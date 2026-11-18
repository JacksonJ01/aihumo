"""Platform-appropriate writable locations for installed AIHuMo builds."""
from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIRECTORY_NAME = "AIHuMo"


def user_data_dir() -> Path:
    """Return the per-user writable AIHuMo data directory.

    ``AIHUMO_USER_DATA_DIR`` is intentionally supported for automated tests,
    managed deployments, and portable installations that explicitly opt in.
    """
    override = os.environ.get("AIHUMO_USER_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIRECTORY_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRECTORY_NAME
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "aihumo"


def default_processed_root() -> Path:
    """Return the default location for user-generated processing outputs."""
    return user_data_dir() / "data" / "processed"


def installer_bootstrap_path(state_dir: Path | None = None) -> Path:
    """Return the setup plan written by a native installer."""
    return (state_dir or user_data_dir()) / "installer-bootstrap.json"
