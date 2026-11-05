import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from app import backup, worker
from app.config import Settings, get_settings
from app.tasks import HANDLERS


def test_command_keeps_password_off_the_command_line():
    cmd, env = backup.dump_command("postgresql+psycopg://dates:s3cret@db:5432/dates", Path("/data/backups/x.part"))
    assert cmd[:3] == ["pg_dump", "-Fc", "--no-owner"]
    assert cmd[cmd.index("-h") + 1] == "db" and cmd[cmd.index("-U") + 1] == "dates"
    assert cmd[-1] == "dates"
    assert "s3cret" not in " ".join(cmd)
    assert env == {"PGPASSWORD": "s3cret"}


def test_prune_keeps_newest_seven_and_manual_dumps(tmp_path):
    for d in range(1, 11):
        (tmp_path / f"dates-2026-11-{d:02d}-0230.dump").write_bytes(b"x")
    (tmp_path / "pre-cleanup-2026-10-30.dump").write_bytes(b"x")
    removed = backup.prune(tmp_path)
    assert removed == [f"dates-2026-11-{d:02d}-0230.dump" for d in (1, 2, 3)]
    left = sorted(p.name for p in tmp_path.iterdir())
    assert len(left) == 8 and "pre-cleanup-2026-10-30.dump" in left


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    s = Settings(data_dir=tmp_path, database_url="postgresql+psycopg://dates:pw@db:5432/dates")
    monkeypatch.setattr(backup, "get_settings", lambda: s)
    return tmp_path


def test_run_backup_writes_file_and_prunes(data_dir, monkeypatch):
    folder = data_dir / "backups"
    folder.mkdir()
    for d in range(1, 8):
        (folder / f"dates-2026-10-{d:02d}-0230.dump").write_bytes(b"old")

    def fake_run(cmd, **kw):
        Path(cmd[cmd.index("-f") + 1]).write_bytes(b"dump")
        assert kw["env"]["PGPASSWORD"] == "pw"
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    r = backup.run_backup(datetime(2026, 11, 5, 2, 30))
    assert r["file"] == "dates-2026-11-05-0230.dump" and r["pruned"] == ["dates-2026-10-01-0230.dump"]
    assert (folder / r["file"]).read_bytes() == b"dump"
    assert not list(folder.glob("*.part"))


def test_failed_dump_leaves_no_partial_file(data_dir, monkeypatch):
    def boom(cmd, **kw):
        Path(cmd[cmd.index("-f") + 1]).write_bytes(b"half")
        raise subprocess.CalledProcessError(1, cmd, stderr="pg_dump: error: connection refused\n")
    monkeypatch.setattr(backup.subprocess, "run", boom)
    with pytest.raises(backup.BackupError, match="connection refused"):
        backup.run_backup(datetime(2026, 11, 5, 2, 30))
    assert not list((data_dir / "backups").iterdir())


def test_missing_pg_dump_is_a_clear_error(data_dir, monkeypatch):
    def nope(cmd, **kw):
        raise FileNotFoundError("pg_dump")
    monkeypatch.setattr(backup.subprocess, "run", nope)
    with pytest.raises(backup.BackupError, match="not installed"):
        backup.run_backup()


def test_job_is_registered_and_scheduled():
    assert "backup" in HANDLERS
    assert "backup" in {j.id for j in worker.make_scheduler().get_jobs()}
