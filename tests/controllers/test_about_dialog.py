"""
This application's identity, and the Help menu wiring that shows it.

The About *dialog* itself moved to bookindexcore in extraction phase 1, and its
own behaviour -- rendering an identity, swapping logo ink with the theme,
surviving a missing asset -- is tested there, against a synthetic identity.
What cannot move is everything on this page: that this application's version
constants are populated, that they match the Inno Setup script that cannot
import them, and that the Help menu reaches the shared controller with this
application's identity in hand.

Driven directly rather than through a real click. AboutDialog is modal, so
anything that reached .exec() would hang the run headlessly (see
tests/README.md) -- show_about() calls .show(), which does not block, and
that is what these drive.
"""
import pytest

from bookindexcore.ui.help.controller import HelpController
from bookindexcore.ui.identity import AppIdentity
from models.app_paths import get_app_root
from models.app_version import (
    APP_COPYRIGHT,
    APP_LICENCE,
    APP_NAME,
    APP_URL,
    APP_VERSION,
    app_identity,
    version_string,
)
from views.main_menu_bar import MainMenuBar


class TestAppVersionModule:
    """
    The version is stated in two places that cannot import each other --
    here, and MyAppVersion in installer/LatexIndexingEditor.iss. These pin
    the shape of what the About box reports so a malformed value is caught
    before it is read off a screenshot in a bug report.
    """

    def test_version_string_is_prefixed(self):
        assert version_string() == f"Version {APP_VERSION}"

    def test_identity_fields_are_populated(self):
        for value in (APP_NAME, APP_VERSION, APP_URL, APP_COPYRIGHT, APP_LICENCE):
            assert value and value.strip()

    def test_installer_version_matches_the_module(self):
        """
        The .iss cannot read the Python module, so the two are kept in step
        by hand -- which is exactly the kind of thing that silently drifts.
        """
        from pathlib import Path

        iss = Path(__file__).resolve().parents[2] / "installer" / "LatexIndexingEditor.iss"
        text = iss.read_text(encoding="utf-8", errors="replace")
        assert f'#define MyAppVersion "{APP_VERSION}"' in text


class TestAppIdentityFactory:
    """
    ``app_identity()`` is the adapter between this application's constants
    and the shape bookindexcore's shared About box takes. It is a function rather
    than a constant because the logo paths come from ``get_app_root()``,
    which must be called from a module inside the application -- moved into
    the shared package it would resolve into site-packages (design document
    section 7.3).
    """

    def test_it_carries_this_applications_facts(self):
        identity = app_identity()

        assert isinstance(identity, AppIdentity)
        assert identity.name == APP_NAME
        assert identity.version == APP_VERSION
        assert identity.url == APP_URL
        assert identity.version_string() == version_string()

    def test_the_wordmarks_it_names_actually_exist(self):
        """
        A missing logo degrades to text rather than crashing, so nothing
        else would report this -- and the About box is often the first thing
        opened when something is already wrong.
        """
        identity = app_identity()

        assert identity.logo_dark_ink.is_file(), identity.logo_dark_ink
        assert identity.logo_light_ink.is_file(), identity.logo_light_ink

    def test_the_paths_are_resolved_from_the_app_root_not_the_package(self):
        """
        The specific hazard section 7.3 exists for: a logo path resolving
        into site-packages works in a frozen build and silently breaks in
        development.
        """
        identity = app_identity()

        assert get_app_root() in identity.logo_dark_ink.parents
        assert "site-packages" not in str(identity.logo_dark_ink)


class TestHelpMenuWiring:
    @staticmethod
    def _window(qtbot):
        """MainMenuBar binds File > Exit to its parent window's close(),
        so it cannot be constructed parentless."""
        from views.latex_editor import LatexEditor

        window = LatexEditor()
        qtbot.addWidget(window)
        return window

    @classmethod
    def _menu_bar(cls, qtbot):
        return MainMenuBar(cls._window(qtbot))

    @classmethod
    def _controller(cls, qtbot):
        window = cls._window(qtbot)
        return HelpController(
            window=window,
            app_root=get_app_root(),
            identity=app_identity(),
        )

    def test_the_menu_exposes_an_about_action(self, qtbot):
        bar = self._menu_bar(qtbot)

        assert bar.about_action.text().startswith("&About")
        assert APP_NAME in bar.about_action.text()

    def test_triggering_it_emits_about_requested(self, qtbot):
        bar = self._menu_bar(qtbot)

        with qtbot.waitSignal(bar.about_requested, timeout=500):
            bar.about_action.trigger()

    def test_about_is_not_gated_behind_an_open_project(self, qtbot):
        """
        Like Help > Contents, and unlike the Tools actions -- the About box
        describes the application, not the project.
        """
        bar = self._menu_bar(qtbot)

        bar.update_menu_item_state(is_enabled=False)

        assert bar.about_action.isEnabled() is True

    def test_controller_creates_the_dialog_once_and_reuses_it(self, qtbot, qapp):
        controller = self._controller(qtbot)

        assert controller.about_dialog is None
        controller.show_about()
        first = controller.about_dialog
        assert first is not None

        controller.show_about()

        assert controller.about_dialog is first
        first.close()

    def test_an_open_about_dialog_follows_a_theme_change(self, qtbot):
        controller = self._controller(qtbot)
        controller.show_about()

        controller._on_theme_changed(True)

        assert "#8AB4F8" in controller.about_dialog._link_label.text()
        controller.about_dialog.close()

    def test_the_dialog_shows_this_applications_name(self, qtbot):
        """
        End to end: the app's constants reach the shared dialog. The dialog
        renders whatever identity it is given -- that it is given the right
        one is this application's responsibility, and this is where it is
        checked.
        """
        from PySide6.QtWidgets import QLabel

        controller = self._controller(qtbot)
        controller.show_about()

        shown = " ".join(
            label.text() for label in controller.about_dialog.findChildren(QLabel)
        )

        assert APP_NAME in shown
        assert APP_VERSION in shown
        controller.about_dialog.close()

    def test_the_help_window_reads_this_applications_help_directory(self, qtbot):
        """
        The other half of the injection: help content lives beside the
        application, not beside the shared package.
        """
        controller = self._controller(qtbot)

        assert controller._help_root == get_app_root() / "help"
        assert controller._help_root.is_dir()
