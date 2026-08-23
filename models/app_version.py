"""
The application's version and identity, in one place.

Previously the version existed only as a #define in
installer/LatexIndexingEditor.iss, which was fine while nothing in the
running application needed to state it. The About box does, and reading it
from the installer script is not possible, so this module is the source of
truth and the installer's own MyAppVersion has to be kept in step with it.
"""

APP_NAME = "LaTeX Indexing Editor"
APP_VERSION = "0.3.0-alpha"
APP_PUBLISHER = "DH Indexing"
APP_TAGLINE = "Back-of-book indexing for LaTeX manuscripts"
APP_URL = "https://github.com/DWHowes/LaTeX_Indexing_Editor"
APP_COPYRIGHT = "Copyright © 2026 Donald Howes"
APP_LICENCE = "MIT Licence"


def version_string() -> str:
    """e.g. 'Version 0.3.0-alpha' -- the form shown in the About box."""
    return f"Version {APP_VERSION}"


def app_identity():
    """
    This application's identity, in the form bookindexcore's shared About box
    takes.

    Built here rather than in the shared package because the package must not
    know which application it is inside, and built as a function rather than a
    module-level constant because the logo paths come from
    ``app_paths.get_app_root()`` -- which is correct only when called from a
    module sitting one directory below the application root, and so is
    deliberately not importable from bookindexcore at all (design document 7.3).
    """
    from bookindexcore.ui.identity import AppIdentity

    from models.app_paths import get_app_root

    icons = get_app_root() / "icons"
    return AppIdentity(
        name=APP_NAME,
        version=APP_VERSION,
        tagline=APP_TAGLINE,
        url=APP_URL,
        copyright=APP_COPYRIGHT,
        licence=APP_LICENCE,
        publisher=APP_PUBLISHER,
        logo_dark_ink=icons / "lix_wordmark_dark_ink.png",
        logo_light_ink=icons / "lix_wordmark_light_ink.png",
    )
