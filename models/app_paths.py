import sys
from pathlib import Path


def get_app_root() -> Path:
    """
    Returns the application's root directory -- the folder containing
    main.py in a normal source checkout, or the folder containing the
    frozen executable when running from a PyInstaller build. Bundled
    resources (data/, help/, icons/) must be looked up relative to this,
    not relative to any individual module's __file__: a frozen module's
    __file__ points into PyInstaller's internal bundle, not the original
    source tree, so a "__file__ two levels up" trick that works in dev
    silently breaks once packaged.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
