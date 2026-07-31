"""
The application's version and identity, in one place.

Previously the version existed only as a #define in
installer/LatexIndexingEditor.iss, which was fine while nothing in the
running application needed to state it. The About box does, and reading it
from the installer script is not possible, so this module is the source of
truth and the installer's own MyAppVersion has to be kept in step with it.
"""

APP_NAME = "LaTeX Indexing Editor"
APP_VERSION = "0.2.0-alpha"
APP_PUBLISHER = "DH Indexing"
APP_TAGLINE = "Back-of-book indexing for LaTeX manuscripts"
APP_URL = "https://github.com/DWHowes/LaTeX_Indexing_Editor"
APP_COPYRIGHT = "Copyright © 2026 Donald Howes"
APP_LICENCE = "MIT Licence"


def version_string() -> str:
    """e.g. 'Version 0.2.0-alpha' -- the form shown in the About box."""
    return f"Version {APP_VERSION}"
