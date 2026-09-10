r"""
Where this application's session log goes, and who decides.

`bookindexcore.session.logger.SessionLogger` captures stdout and stderr to a
timestamped file and needs one thing from its host: **where to put it**. It
used to guess, falling back to ``os.getcwd()/session_logs``, and on 5 September
2026 that put a folder of this application's logs into an unrelated directory
somebody had launched it from. The core refuses to guess now, so this module is
the answer.

#### Two places, because a session has two halves

**The indexer's rule is that session logs belong in a sub-folder of the open
project**, and a LaTeX project folder is the indexer's own workspace, so that
is plainly right. But a session starts before any project is open and carries
on after one closes, and *the startup half is the half most likely to be worth
reading*: it holds the preferences migration, the store adoption, and any
exception that stopped a project from opening at all.

So the log starts here, in this application's own user-data folder, moves under
the project when one opens, and **comes back here when it closes**. The move
back is the caller nothing had: until 10 September 2026 the log went into a
project and stayed there, so after closing it the session went on writing into
a folder the indexer had finished with.

#### Local, and inside the suite's folder

`bookindexcore.store.location.vendor_root` is the one encoding of where this
suite keeps a user's working files: ``%LOCALAPPDATA%\DH Indexing`` on Windows
and the platform's own convention elsewhere. Local rather than Roaming, on the
argument the store module makes about itself: a log file has no business being
copied between machines at logout.
"""

from __future__ import annotations

import os
from pathlib import Path

from bookindexcore.store.location import vendor_root

from models.app_version import APP_NAME

__all__ = ["LOG_ENV", "LOG_FOLDER_NAME", "app_data_root", "folder_name",
           "log_root", "start_logging"]

#: Point the log somewhere else. Tests use it, and so does anyone who wants
#: their logs on a different drive. The Word editor's `WORDINDEX_LOG_DIR` in
#: this application's spelling.
LOG_ENV = "LATEXINDEX_LOG_DIR"

#: The folder's name when nobody has said otherwise. **The indexer can rename
#: it**, on the General preferences page, which is what `folder_name` reads.
LOG_FOLDER_NAME = "session_logs"


def app_data_root() -> Path:
    """
    This application's own folder inside the suite's user-data directory.

    The *parent* of the log folder, not the log folder itself, because that is
    what `SessionLogger.relocate_to` takes: it appends the folder name in
    force, so the same call works whether or not the indexer has renamed it.
    """
    override = os.environ.get(LOG_ENV)
    if override:
        return Path(override)
    return vendor_root() / APP_NAME


def folder_name() -> str:
    """
    What the log folder is called, the indexer's answer if they gave one.

    Guarded, and it falls back rather than raising: logging is the thing that
    reports a failure, so a failure *inside* it must leave the application
    running and logging somewhere rather than not at all.

    ***Read here and not at construction time.*** The logger is deliberately
    built before `QApplication` exists, because the output it captures starts
    before that; `QSettings` needs the organisation and application names that
    `QApplication` sets. So the session starts under whatever this returns and
    `apply_general_preferences` moves it once the preference is readable.
    """
    try:
        from PySide6.QtCore import QSettings

        stored = str(QSettings().value("log_directory_name", "") or "").strip()
        return stored or LOG_FOLDER_NAME
    except Exception:                                         # noqa: BLE001
        return LOG_FOLDER_NAME


def log_root() -> Path:
    """The folder session logs are written into before a project opens."""
    return app_data_root() / folder_name()


def start_logging():
    """
    Begin capturing this session's console output, or carry on without it.

    **A logger that cannot write must not stop the application.** An installed
    copy can find its data directory read-only or on a network share that is
    not mounted yet, and an indexer meeting a dead application with no window
    and no message has no way to find out why. Until 10 September 2026 the
    construction sat one line above `main.py`'s ``try:`` and an unwritable
    location killed startup silently.

    The core degrades on its own now; this guard is for the rest, an import
    that fails or a user-data root that cannot be resolved at all.

    Returns the logger, or None.
    """
    try:
        from bookindexcore.session.logger import SessionLogger

        return SessionLogger(target_directory=str(log_root()),
                             folder_name=folder_name())
    except Exception as failure:                              # noqa: BLE001
        print(f"[SESSION LOG] Not logging this session: {failure}")
        return None
