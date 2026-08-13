r"""
The two shared preferences pages, as this application mounts them.

The pages themselves are tested in ``bookindexcore``. What is only true here
is the wiring, and it is the wiring that fails quietly: ``tab_order()`` is
declared rather than derived, so a page added to the shared shell does **not**
appear in this window until it is named -- and the failure looks like nothing
at all, an unchanged dialog with a working new feature behind it.
"""

from PySide6.QtWidgets import QTabBar

from bookindexcore.checks import ALL_RULES, DISABLED_RULES_KEY
from bookindexcore.sorting import LETTER_BY_LETTER, ORDER_MODE_KEY

from views.index_prefs_config_dialog import IndexPrefsConfigDialog


def _dialog(qtbot):
    dialog = IndexPrefsConfigDialog()
    qtbot.addWidget(dialog)
    return dialog


class TestTheWindowMountsThem:
    def test_the_declared_order_includes_the_shared_pages(self, qtbot):
        dialog = _dialog(qtbot)
        labels = [dialog.vertical_tabs.tabText(i)
                  for i in range(dialog.vertical_tabs.count())]
        assert labels == ["General", "Check Index", "Sorting",
                          "LaTeX Settings", "UI Themes", "RTF Export"]

    def test_a_latex_page_still_sits_on_each_side_of_themes(self, qtbot):
        """
        The reason `tab_order()` is declared rather than merged: no
        append-based shell can express this, and reordering it would take the
        user guide's screenshots with it.
        """
        dialog = _dialog(qtbot)
        labels = [dialog.vertical_tabs.tabText(i) for i in range(6)]
        assert labels.index("LaTeX Settings") < labels.index("UI Themes")
        assert labels.index("RTF Export") > labels.index("UI Themes")

    def test_six_tabs_still_fit(self, qtbot):
        """
        A West tab bar's height is the sum of its rotated labels' widths.
        Six of these labels overflowed a 580-tall window on a large font, and
        Qt's answer was a scroll arrow with RTF Export behind it.
        """
        dialog = _dialog(qtbot)
        bar = dialog.vertical_tabs.findChild(QTabBar)
        assert not bar.usesScrollButtons()
        assert bar.tabRect(bar.count() - 1).bottom() <= bar.sizeHint().height()


class TestTheStrategyControlPointsAtTheRealSwitch:
    def test_it_is_read_only_here(self, qtbot):
        """
        `makeindex_ordering` on the LaTeX Settings page has held this choice
        since before the shared page existed. Two editable copies would
        disagree the first time either was changed.
        """
        dialog = _dialog(qtbot)
        assert not dialog.sorting_tab.cmb_alphabetising.isEnabled()

    def test_it_names_where_the_real_one_is(self, qtbot):
        dialog = _dialog(qtbot)
        source = dialog.alphabetising_source()
        assert "LaTeX Settings" in source
        assert "Sort Ordering Rule" in source

    def test_the_value_still_round_trips(self, qtbot):
        """
        Read-only is not omitted. This application overrides `alphabetising`
        from `makeindex_ordering` on the way out, but the page must still
        report it or an OK would look like a deletion.
        """
        dialog = _dialog(qtbot)
        dialog.populate_sorting_fields({"alphabetising": LETTER_BY_LETTER})
        assert dialog.collect_project_payload()["alphabetising"] == LETTER_BY_LETTER


class TestTheMergedPayload:
    def test_it_carries_all_three_groups(self, qtbot):
        dialog = _dialog(qtbot)
        dialog.populate_fields({})
        dialog.populate_check_index_fields({})
        dialog.populate_sorting_fields({})

        payload = dialog.collect_project_payload()
        assert DISABLED_RULES_KEY in payload        # Check Index
        assert ORDER_MODE_KEY in payload            # Sorting
        assert "makeindex_ordering" in payload      # LaTeX

    def test_every_rule_reaches_a_control(self, qtbot):
        dialog = _dialog(qtbot)
        assert set(dialog.check_index_tab._rule_boxes) == {
            rule.id for rule in ALL_RULES}


class TestTheOrderingVocabulary:
    def test_the_combo_offers_makeindexs_own_two_words(self, qtbot):
        dialog = _dialog(qtbot)
        combo = dialog.cmb_makeindex_order
        assert [combo.itemText(i) for i in range(combo.count())] == [
            "word", "letter"]

    def test_the_old_spelling_is_read_and_upgraded(self, qtbot):
        """
        `character` was the second item before the shared Sorting page went
        in, and nothing else in the application spelled it that way. A
        project saved then is read here and re-saved under the new spelling,
        so the migration costs no schema.
        """
        dialog = _dialog(qtbot)
        dialog.populate_fields({"makeindex_ordering": "character"})
        assert dialog.cmb_makeindex_order.currentText() == "letter"
        assert dialog.collect_host_payload()["makeindex_ordering"] == "letter"
