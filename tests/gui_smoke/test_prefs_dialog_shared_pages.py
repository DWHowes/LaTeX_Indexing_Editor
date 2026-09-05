r"""
The shared preferences pages, as this application mounts them.

The pages themselves are tested in ``bookindexcore``. What is only true here
is the wiring, and the wiring has failed in both directions. It used to fail
by *absence*: ``tab_order()`` was declared rather than composed, so a page
added to the shared shell did not appear in this window until it was named,
and the failure looked like nothing at all -- an unchanged dialog with a
working new feature behind it. Composing it fixed that and introduced the
opposite failure, where a page arrived in an application that had no use for
it. Both are tested below.
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
    def test_the_shared_pages_come_first_and_the_latex_ones_are_appended(self, qtbot):
        dialog = _dialog(qtbot)
        labels = [dialog.vertical_tabs.tabText(i)
                  for i in range(dialog.vertical_tabs.count())]
        assert labels == ["General", "Checks", "Sorting", "Presentation",
                          "Authorities", "UI Themes", "LaTeX", "RTF"]

    def test_no_latex_page_is_mixed_into_the_shared_block(self, qtbot):
        """
        The rule that replaced the declared order. It used to be General,
        Check Index, Sorting, LaTeX Settings, UI Themes, RTF Export -- a LaTeX
        page on either side of the shared Themes page -- and two things were
        wrong with that. A page added to the shell did not appear here until
        it was named, which is how E8's Presentation page came to be missing,
        and the failure is silent because an absent tab looks like one that
        was never built. And *shared* and *ours* were not distinguishable in
        the window, so the same page sat in a different neighbourhood in each
        application.

        The cost was one reorder, and it takes the user guide's preferences
        screenshots with it.

        The shared set is asked for rather than written down. It used to be a
        literal, and that made this test fail for a reason it does not test:
        T1b added a "Table of Authorities" page to the shell, the literal did
        not know about it, and a test about *ordering* went red over
        *membership*. What is shared is the shell's to say — this file's
        business is only that all of it comes first.
        """
        dialog = _dialog(qtbot)
        labels = [dialog.vertical_tabs.tabText(i)
                  for i in range(dialog.vertical_tabs.count())]
        shared = {label for label, _ in dialog.shared_tab_order()}
        first_host = min(i for i, l in enumerate(labels) if l not in shared)
        assert all(l in shared for l in labels[:first_host])
        assert not any(l in shared for l in labels[first_host:])

    def test_a_page_added_to_the_shell_arrives_here_without_an_edit(self, qtbot):
        """
        The property the change bought. Overriding `tab_order` is now refused
        outright rather than quietly dropping the pages it does not name.
        """
        from bookindexcore.ui.preferences import PreferencesDialog

        dialog = _dialog(qtbot)
        assert type(dialog).tab_order is PreferencesDialog.tab_order
        labels = [dialog.vertical_tabs.tabText(i)
                  for i in range(dialog.vertical_tabs.count())]
        for label, _widget in dialog.shared_tab_order():
            assert label in labels, label

    def test_this_application_now_gets_a_table_of_authorities_page(self, qtbot):
        """
        **This test used to assert the opposite, and inverting it is the whole
        of what T3b owed the decision that created it.**

        Composing `tab_order` means a shared page arrives here without an edit,
        which is right for a page every index needs and wrong for one only some
        applications can act on: T1b's "Table of Authorities" page landed in
        this window while emission did not exist anywhere. The page was gated
        on `supports_table_of_authorities()`, this application answered False,
        and the assertion was that it had no page and wrote no keys.

        T3b gives it something to generate -- `models.toa_emission` writes
        `\\index[toacases]{...}` and imakeidx builds the table -- so the answer
        is now True, the page is mounted, and the citation standard chosen on
        it decides what this application finds.
        """
        from bookindexcore.ui.preferences.authorities_tab import (
            CITATION_SYSTEM_KEY,
        )

        dialog = _dialog(qtbot)
        labels = [dialog.vertical_tabs.tabText(i)
                  for i in range(dialog.vertical_tabs.count())]

        assert dialog.supports_table_of_authorities()
        assert "Authorities" in labels
        assert CITATION_SYSTEM_KEY in dialog.collect_project_payload()

    def test_all_eight_tabs_fit(self, qtbot):
        """
        A West tab bar's height is the sum of its rotated labels' widths.
        Six of these labels overflowed a 580-tall window on a large font, and
        Qt's answer was a scroll arrow with the last page behind it. E8's
        Presentation page made it seven, T3b's Authorities page eight.
        """
        dialog = _dialog(qtbot)
        bar = dialog.vertical_tabs.findChild(QTabBar)
        assert not bar.usesScrollButtons()
        assert bar.tabRect(bar.count() - 1).bottom() <= bar.sizeHint().height()

    def test_the_labels_are_the_short_ones(self, qtbot):
        """
        Because the window's height depends on them.

        A West tab bar rotates its labels, so the bar's height is the sum of
        their widths and, with its scroller deliberately off, that height is
        a floor the dialog cannot be sized below. Spelled out, *Check Index*
        and *Table of Authorities* put the floor at 746 pixels, and a
        1366x768 laptop has about 730 usable once the task bar and title bar
        are taken off; the short labels put it at 593.

        ***The height itself is not asserted here, because this suite runs
        offscreen and the offscreen platform does not have the machine's font
        metrics*** -- it reports 964 for the same window that measures 593 on
        the real platform, so a pixel threshold in this file would be
        measuring a font nobody has. `probes/prefs_dialog_fits.py` measures
        it where the number means something. What is testable here is the
        input the indexer's window is built from: the labels.
        """
        dialog = _dialog(qtbot)
        labels = [dialog.vertical_tabs.tabText(i)
                  for i in range(dialog.vertical_tabs.count())]
        assert max(len(label) for label in labels) <= len("Presentation")


class TestTheStrategyControlPointsAtTheRealSwitch:
    def test_it_is_read_only_here(self, qtbot):
        """
        `makeindex_ordering` on the LaTeX page has held this choice
        since before the shared page existed. Two editable copies would
        disagree the first time either was changed.
        """
        dialog = _dialog(qtbot)
        assert not dialog.sorting_tab.cmb_alphabetising.isEnabled()

    def test_it_names_where_the_real_one_is(self, qtbot):
        dialog = _dialog(qtbot)
        source = dialog.alphabetising_source()
        assert "LaTeX" in source
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
