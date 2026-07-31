"""
Help > About: the dialog, and the menu-to-controller wiring behind it.

Driven directly rather than through a real click. AboutDialog is modal, so
anything that reached .exec() would hang the run headlessly (see
tests/README.md) -- show_about() calls .show(), which does not block, and
that is what these drive.
"""
import pytest
from PySide6.QtWidgets import QDialog

from controllers.help_controller import HelpController
from models.app_version import (
    APP_COPYRIGHT,
    APP_LICENCE,
    APP_NAME,
    APP_URL,
    APP_VERSION,
    version_string,
)
from views.about_dialog import AboutDialog
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


class TestAboutDialog:
    def test_reports_the_current_version_and_name(self, qtbot):
        from PySide6.QtWidgets import QLabel

        dialog = AboutDialog()
        qtbot.addWidget(dialog)

        shown = " ".join(label.text() for label in dialog.findChildren(QLabel))

        assert APP_VERSION in shown
        assert APP_NAME in shown
        assert APP_URL in shown

    def test_shows_the_wordmark(self, qtbot):
        dialog = AboutDialog()
        qtbot.addWidget(dialog)

        assert dialog._logo_label.pixmap() is not None
        assert not dialog._logo_label.pixmap().isNull()

    def test_swaps_to_the_light_ink_logo_in_dark_mode(self, qtbot):
        """
        The logo is a bitmap in two ink colours rather than one tinted at
        runtime -- tinting composites over Computer Modern's very fine
        antialiased serifs, which is where it goes wrong.
        """
        dialog = AboutDialog()
        qtbot.addWidget(dialog)

        dialog.apply_theme_configuration(False)
        light_mode = dialog._logo_label.pixmap().toImage()
        dialog.apply_theme_configuration(True)
        dark_mode = dialog._logo_label.pixmap().toImage()

        assert light_mode != dark_mode

    def test_link_colour_changes_with_the_theme(self, qtbot):
        """Qt's default <a> colour is unreadable on the dark background."""
        dialog = AboutDialog()
        qtbot.addWidget(dialog)

        dialog.apply_theme_configuration(False)
        assert "#1F3864" in dialog._link_label.text()
        dialog.apply_theme_configuration(True)
        assert "#8AB4F8" in dialog._link_label.text()

    def test_survives_a_missing_logo_file(self, qtbot, monkeypatch):
        """
        The About box is often the first thing opened when something is
        already wrong, so a missing asset must not take it down.
        """
        from PySide6.QtGui import QPixmap

        dialog = AboutDialog()
        qtbot.addWidget(dialog)

        dialog._set_logo(QPixmap())

        assert dialog._logo_label.text() == APP_NAME

    def test_is_a_dialog_that_closes_on_accept(self, qtbot):
        dialog = AboutDialog()
        qtbot.addWidget(dialog)
        assert isinstance(dialog, QDialog)

        dialog.show()
        dialog.accept()

        assert not dialog.isVisible()


class TestHelpMenuWiring:
    @staticmethod
    def _menu_bar(qtbot):
        """MainMenuBar binds File > Exit to its parent window's close(),
        so it cannot be constructed parentless."""
        from views.latex_editor import LatexEditor

        window = LatexEditor()
        qtbot.addWidget(window)
        bar = MainMenuBar(window)
        return bar

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
        from views.latex_editor import LatexEditor

        window = LatexEditor()
        qtbot.addWidget(window)
        controller = HelpController(window=window)

        assert controller.about_dialog is None
        controller.show_about()
        first = controller.about_dialog
        assert first is not None

        controller.show_about()

        assert controller.about_dialog is first
        first.close()

    def test_an_open_about_dialog_follows_a_theme_change(self, qtbot):
        from views.latex_editor import LatexEditor

        window = LatexEditor()
        qtbot.addWidget(window)
        controller = HelpController(window=window)
        controller.show_about()

        controller._on_theme_changed(True)

        assert "#8AB4F8" in controller.about_dialog._link_label.text()
        controller.about_dialog.close()
