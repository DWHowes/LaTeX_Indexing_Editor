"""
Dark-mode dialogs must keep their affordances visible.

Styling a widget in the shared dialog sheet takes its rendering away from the
native style, and anything the sheet does not then redraw disappears. That has
now bitten three separate affordances -- the focus ring, the default button's
accent, and the spin/combo arrows -- so these tests measure the rendered pixels
rather than trusting the stylesheet text.

Thresholds are deliberately loose: they are here to catch an affordance
collapsing to invisibility (contrast near 1:1), not to police exact shades.
"""
from collections import Counter
from dataclasses import asdict

import pytest
from PySide6.QtWidgets import QSpinBox, QTabBar

from bookindexcore.ui.style import AppStyleConfiguration
from bookindexcore.ui.theme.config_model import DarkThemeColours, LightThemeColours
from views.index_prefs_config_dialog import IndexPrefsConfigDialog
from bookindexcore.ui.theme.config_dialog import ThemeConfigDialog


def _luminance(rgb):
    def channel(value):
        value /= 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(first, second):
    a, b = _luminance(first), _luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _colour_counts(image, x0, y0, width, height):
    counts = Counter()
    for y in range(y0, min(y0 + height, image.height())):
        for x in range(x0, min(x0 + width, image.width())):
            pixel = image.pixelColor(x, y)
            counts[(pixel.red(), pixel.green(), pixel.blue())] += 1
    return counts


@pytest.fixture
def dark_prefs_dialog(qapp, qtbot):
    AppStyleConfiguration.configure_application_theme(True)
    dialog = IndexPrefsConfigDialog()
    qtbot.addWidget(dialog)
    dialog.apply_theme_configuration(True)
    dialog.resize(760, 580)
    dialog.show()
    qapp.processEvents()
    yield dialog
    AppStyleConfiguration.configure_application_theme(False)


class TestTabSelectionIsVisible:
    def test_selected_tab_differs_from_the_others(self, dark_prefs_dialog, qapp):
        bar = dark_prefs_dialog.vertical_tabs.findChild(QTabBar)
        bar.setCurrentIndex(0)
        qapp.processEvents()

        image = bar.grab().toImage()

        def background(index):
            rect = bar.tabRect(index)
            inner = _colour_counts(image, rect.x() + 4, rect.y() + 4,
                                   rect.width() - 8, rect.height() - 8)
            return inner.most_common(1)[0][0]

        selected = background(0)
        others = [background(i) for i in range(1, bar.count())]

        assert others, "expected more than one tab to compare against"
        for index, other in enumerate(others, start=1):
            ratio = _contrast(selected, other)
            assert ratio >= 2.0, (
                f"selected tab {selected} is nearly identical to unselected tab "
                f"{index} {other} ({ratio:.2f}:1) -- which tab is in front is "
                f"not discernible")

    def test_selection_tracks_the_current_tab(self, dark_prefs_dialog, qapp):
        bar = dark_prefs_dialog.vertical_tabs.findChild(QTabBar)

        def background_of_current():
            image = bar.grab().toImage()
            rect = bar.tabRect(bar.currentIndex())
            return _colour_counts(image, rect.x() + 4, rect.y() + 4,
                                  rect.width() - 8, rect.height() - 8).most_common(1)[0][0]

        bar.setCurrentIndex(0)
        qapp.processEvents()
        first = background_of_current()

        bar.setCurrentIndex(2)
        qapp.processEvents()
        third = background_of_current()

        assert first == third, "the highlight should follow the selected tab"


class TestThemeConfigDialogTabs:
    """The theme editor was the one dialog not applying the shared sheet, so
    its Dark/Light tabs kept the native rendering -- 1.10:1, the same problem
    by a different route. Its preview panel styles itself and must stay
    independent of the live theme, which is why the sheet is safe here."""

    @pytest.fixture
    def dialog(self, qapp, qtbot):
        AppStyleConfiguration.configure_application_theme(True)
        dlg = ThemeConfigDialog(
            dark_colours=asdict(DarkThemeColours()),
            light_colours=asdict(LightThemeColours()),
        )
        qtbot.addWidget(dlg)
        dlg.resize(820, 600)
        dlg.show()
        qapp.processEvents()
        yield dlg
        AppStyleConfiguration.configure_application_theme(False)

    def test_it_applies_the_shared_dialog_sheet(self, dialog):
        assert dialog.styleSheet().strip(), (
            "the theme editor no longer picks up the shared dialog sheet, so its "
            "tabs and default button lose their affordances in dark mode")

    def test_selected_tab_differs_from_the_other(self, dialog, qapp):
        bar = dialog.findChild(QTabBar)
        bar.setCurrentIndex(0)
        qapp.processEvents()

        image = bar.grab().toImage()

        def background(index):
            rect = bar.tabRect(index)
            return _colour_counts(image, rect.x() + 6, rect.y() + 6,
                                  rect.width() - 12, rect.height() - 12).most_common(1)[0][0]

        ratio = _contrast(background(0), background(1))
        assert ratio >= 2.0, (
            f"Dark/Light tabs are {ratio:.2f}:1 apart -- which one is in front "
            f"is not discernible")


class TestSpinBoxArrowsAreVisible:
    def test_arrows_contrast_against_their_button(self, dark_prefs_dialog, qapp):
        spin = dark_prefs_dialog.findChildren(QSpinBox)[0]
        # Away from either end, so neither arrow is legitimately greyed out --
        # a disabled arrow is meant to be dim and would mask the real problem.
        spin.setValue((spin.minimum() + spin.maximum()) // 2)
        qapp.processEvents()

        image = spin.grab().toImage()

        # The up/down buttons sit at the trailing edge of the widget.
        strip_width = 20
        counts = _colour_counts(image, image.width() - strip_width, 1,
                                strip_width, image.height() - 2)
        background = counts.most_common(1)[0][0]
        # The arrow is the lightest colour drawn in the button area. An
        # absolute floor rather than a percentage: the arrows are small, and a
        # percentage of the strip scales with the widget's height, which would
        # quietly stop looking at the arrow core on a taller spin box.
        substantial = [c for c, n in counts.items() if n >= 3]
        arrow = max(substantial, key=_luminance)

        ratio = _contrast(arrow, background)
        assert ratio >= 3.0, (
            f"spin arrows {arrow} on {background} are {ratio:.2f}:1 -- styling "
            f"QSpinBox in the dialog sheet takes its sub-controls away from the "
            f"native style and leaves the arrows drawn in the frame colour")


class TestSheetDoesNotClaimSubControls:
    """Structural guard for the same regression, stated as the rule itself."""

    def test_dark_sheet_leaves_spin_and_combo_to_the_native_style(self):
        sheet = AppStyleConfiguration.get_dialog_stylesheet(DarkThemeColours())

        for widget in ("QSpinBox", "QComboBox"):
            for line in sheet.splitlines():
                stripped = line.strip()
                if stripped.startswith("/*") or stripped.startswith("*"):
                    continue
                if widget in stripped and "{" in stripped:
                    pytest.fail(
                        f"{widget} is styled in the dark dialog sheet ({stripped!r}). "
                        f"Any box property on it hands its arrows to the stylesheet "
                        f"engine, which draws them in the frame colour. Restore them "
                        f"explicitly with images if this is intentional.")

    def test_light_mode_still_uses_native_rendering(self):
        assert AppStyleConfiguration.get_dialog_stylesheet(LightThemeColours()) == ""
