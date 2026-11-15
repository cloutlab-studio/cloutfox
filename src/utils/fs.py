"""File helpers that survive Windows.

Windows refuses to delete or replace a file another process holds, and marks
some files read-only (a browser's cache and lock files among them). A plain
`shutil.rmtree` then leaves half a directory behind, and the next start
inherits it: a stale fingerprint, a half-packed profile, a profile that cannot
be deleted. These helpers clear the attribute and retry briefly.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import stat
import time
from typing import IO

from ..core.logging import get_logger

logger = get_logger("utils.fs")

ATTEMPTS = 4
DELAY = 0.25
# Files and folders holding cookies, proxies and keys: the owner only. Linux and
# macOS honour the mode; on Windows the folder's ACL already does (chmod sets
# nothing but the read-only bit there).
PRIVATE_FILE = 0o600
PRIVATE_DIR = 0o700


def make_private(path: str | pathlib.Path) -> None:
    """Restrict a folder to its owner."""
    with contextlib.suppress(OSError):
        pathlib.Path(path).chmod(PRIVATE_DIR)


def open_private(path: str | pathlib.Path) -> IO[bytes]:
    """Open a file for writing so only the owner can read it from the start."""
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE)
    with contextlib.suppress(OSError):
        os.chmod(target, PRIVATE_FILE)
    return os.fdopen(fd, "wb")


def write_private(path: str | pathlib.Path, data: bytes) -> None:
    """Write bytes no one else can read, flushed to disk before the rename."""
    with open_private(path) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def clear_read_only(root: pathlib.Path) -> None:
    """Make every entry writable so it can be deleted (no-op where it already is)."""
    if not root.exists():
        return
    try:
        entries = [root, *root.rglob("*")] if root.is_dir() else [root]
    except OSError:
        return
    for path in entries:
        try:
            if path.is_symlink():
                continue
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        except OSError:
            continue


def remove_tree(path: str | pathlib.Path) -> bool:
    """Remove a directory tree; True when it is gone.

    A lock held by another process (a browser still dying, an antivirus reading
    the files) gets a few short retries instead of a silent half-delete.
    """
    target = pathlib.Path(path)
    for i in range(ATTEMPTS):
        try:
            shutil.rmtree(target)
            return True
        except FileNotFoundError:
            return True
        except OSError as e:
            if i == ATTEMPTS - 1:
                logger.warning("Could not remove %s after %s tries: %s", target, ATTEMPTS, e)
                return False
            clear_read_only(target)
            time.sleep(DELAY * (i + 1))
    return False
