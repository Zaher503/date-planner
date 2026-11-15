import os
import subprocess

import pytest

from app import worker, ytdlp_update
from app.config import get_settings
from app.tasks import HANDLERS


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    return tmp_path


def test_no_self_updated_copy_means_default_environment(data_dir):
    assert ytdlp_update.run_env() is None


def test_updated_copy_goes_first_on_the_path(data_dir, monkeypatch):
    (data_dir / "ytdlp").mkdir()
    monkeypatch.setenv("PYTHONPATH", "/other")
    env = ytdlp_update.run_env()
    assert env["PYTHONPATH"].split(os.pathsep)[0].endswith("ytdlp")
    assert "/other" in env["PYTHONPATH"].split(os.pathsep)


def _fake_run(versions, pip_fails=False):
    """Stand-in for subprocess.run: pip fills the target folder, the version probe reads `versions`."""
    def run(cmd, **kw):
        if "pip" in cmd:
            if pip_fails:
                raise subprocess.CalledProcessError(1, cmd, stderr="ERROR: no network\n")
            target = cmd[cmd.index("--target") + 1]
            import pathlib
            pathlib.Path(target).mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        v = versions.pop(0)
        if v is None:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, v + "\n", "")
    return run


def test_update_swaps_in_the_new_copy(data_dir, monkeypatch):
    (data_dir / "ytdlp").mkdir()
    (data_dir / "ytdlp" / "old.txt").write_text("x")
    monkeypatch.setattr(subprocess, "run", _fake_run(["2025.10.01", "2025.11.01"]))
    out = ytdlp_update.run_update()
    assert out == {"before": "2025.10.01", "after": "2025.11.01", "changed": True}
    assert (data_dir / "ytdlp").is_dir() and not (data_dir / "ytdlp" / "old.txt").exists()
    assert not (data_dir / "ytdlp.new").exists() and not (data_dir / "ytdlp.old").exists()


def test_broken_new_copy_keeps_the_old_one(data_dir, monkeypatch):
    (data_dir / "ytdlp").mkdir()
    (data_dir / "ytdlp" / "old.txt").write_text("x")
    monkeypatch.setattr(subprocess, "run", _fake_run(["2025.10.01", None]))
    with pytest.raises(ytdlp_update.UpdateError):
        ytdlp_update.run_update()
    assert (data_dir / "ytdlp" / "old.txt").exists() and not (data_dir / "ytdlp.new").exists()


def test_pip_failure_is_reported_and_leaves_nothing_behind(data_dir, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(["2025.10.01"], pip_fails=True))
    with pytest.raises(ytdlp_update.UpdateError, match="no network"):
        ytdlp_update.run_update()
    assert not (data_dir / "ytdlp.new").exists()


def test_weekly_job_is_registered_and_scheduled():
    assert "ytdlp_update" in HANDLERS
    job = worker.make_scheduler().get_job("ytdlp_update")
    assert job is not None and "day_of_week='sun'" in str(job.trigger)
