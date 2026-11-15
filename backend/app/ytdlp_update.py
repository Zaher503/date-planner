"""Weekly yt-dlp self-update.

TikTok and YouTube change often and old yt-dlp releases stop working, so the worker installs
the newest release into DATA_DIR/ytdlp (a volume, so it survives restarts). Downloads put that
folder first on PYTHONPATH (see media._yt_dlp); the version baked into the image is the fallback.
"""
import logging
import os
import shutil
import subprocess
import sys

from app.config import get_settings

log = logging.getLogger(__name__)

INSTALL_TIMEOUT_S = 300


class UpdateError(RuntimeError):
    pass


def update_dir():
    return get_settings().data_dir / "ytdlp"


def run_env() -> dict | None:
    """Environment for a yt-dlp run that prefers the self-updated copy; None when there is none."""
    d = update_dir()
    if not d.is_dir():
        return None
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(d), env.get("PYTHONPATH", "")) if p)
    return env


def _version(env: dict | None) -> str | None:
    try:
        out = subprocess.run([sys.executable, "-c", "import yt_dlp.version as v; print(v.__version__)"],
                             check=True, capture_output=True, text=True, timeout=60, env=env)
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip() or None


def run_update() -> dict:
    """Install the latest release beside the current one; swap it in only if it imports."""
    final = update_dir()
    staging = final.with_name(final.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    before = _version(run_env())
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir",
                        "--disable-pip-version-check", "--target", str(staging), "yt-dlp"],
                       check=True, capture_output=True, text=True, timeout=INSTALL_TIMEOUT_S)
    except subprocess.CalledProcessError as e:
        shutil.rmtree(staging, ignore_errors=True)
        tail = (e.stderr or "").strip().splitlines()[-1:] or ["no output"]
        raise UpdateError(f"pip failed: {tail[0][:300]}") from e
    except subprocess.TimeoutExpired as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("pip timed out") from e
    env = dict(os.environ)
    env["PYTHONPATH"] = str(staging)
    after = _version(env)
    if after is None:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("the new yt-dlp does not start; kept the old one")
    old = final.with_name(final.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if final.exists():
        final.rename(old)
    staging.rename(final)
    shutil.rmtree(old, ignore_errors=True)
    log.info("yt-dlp %s -> %s", before, after)
    return {"before": before, "after": after, "changed": before != after}
