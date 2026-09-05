r"""
The two places a syntax finding is shown.

An entry can be created in the Index Entry window or edited in the entry
table, and until now neither said anything at all about what was typed
into it -- a bare "%" reached the printed index as a truncated term with
no page number, having produced no warning at any stage. Both surfaces
now report, in the same words, because both call
``views.index_syntax_advice.advise``.

The Index Entry window additionally offers the repair, because it has
somewhere to click. The table reports and stops there.
"""
import pytest
from PySide6.QtCore import QSettings, Qt

from models import index_syntax_check as syntax
from views.entry_modifier_list import (
    EntryModifierList, COL_MAIN_DISP, COL_MAIN_SORT, COL_SUB1_DISP, COL_ENCAP,
)
from bookindexcore.ui.entry_window import levels
from views.latex_index_window import LatexIndexWindow
from views import index_syntax_advice as advice

MAIN = 0


@pytest.fixture(autouse=True)
def _application(qapp):
    """
    advise() reaches for QApplication.style() to build its icons, so even
    the tests that touch no widget need the application object.
    """


@pytest.fixture
def window(qtbot, monkeypatch):
    store = {}
    monkeypatch.setattr(QSettings, "value",
                        lambda self, key, default=None, type=None: store.get(key, default))
    monkeypatch.setattr(QSettings, "setValue",
                        lambda self, key, value: store.__setitem__(key, value))

    view = LatexIndexWindow()
    qtbot.addWidget(view)
    view.show()
    return view


@pytest.fixture
def table(qtbot):
    view = EntryModifierList()
    qtbot.addWidget(view)
    return view


def _has_icon(item) -> bool:
    icon = item.data(Qt.ItemDataRole.DecorationRole)
    return icon is not None and not icon.isNull()


class TestTheAdviceItself:
    def test_clean_text_asks_for_nothing(self):
        assert advice.advise("negligence", role=syntax.ROLE_DISPLAY) == (None, "", False)

    def test_the_tooltip_carries_every_message(self):
        _icon, tooltip, _fixable = advice.advise("50% of R&D", role=syntax.ROLE_DISPLAY)
        assert "2 things to check" in tooltip
        assert "comment" in tooltip
        assert "reserved in LaTeX" in tooltip

    def test_one_finding_is_not_pluralised(self):
        _icon, tooltip, _fixable = advice.advise("50%", role=syntax.ROLE_DISPLAY)
        assert "1 thing to check" in tooltip

    def test_the_messages_are_html_escaped(self):
        """
        They are full of the characters they warn about, and the tooltip
        is rich text so that Qt wraps these sentences rather than running
        them off the screen.
        """
        _icon, tooltip, _fixable = advice.advise("R&D", role=syntax.ROLE_DISPLAY)
        assert "&amp;" in tooltip

    def test_a_fix_hint_is_offered_only_where_a_fix_exists(self):
        hint = "Click this."
        _i, fixable_tooltip, fixable = advice.advise(
            "50%", role=syntax.ROLE_DISPLAY, fix_hint=hint)
        _i, stuck_tooltip, stuck = advice.advise(
            r"\textbf{unclosed", role=syntax.ROLE_DISPLAY, fix_hint=hint)

        assert fixable is True and hint in fixable_tooltip
        assert stuck is False and hint not in stuck_tooltip

    def test_severity_picks_the_icon(self):
        error_icon, _t, _f = advice.advise("50%", role=syntax.ROLE_DISPLAY)
        warning_icon, _t, _f = advice.advise("a|b", role=syntax.ROLE_DISPLAY)
        assert error_icon.cacheKey() != warning_icon.cacheKey()


class TestIndexEntryWindowAdvice:
    def test_every_field_that_reaches_the_macro_is_watched(self, window):
        """All six -- a sort key is never printed, but a "%" in one still
        comments out the rest of the entry."""
        watched = set(window._syntax_notices)
        assert watched == set(window.fields.display_fields) | set(window.sort_entries)

    def test_a_clean_field_shows_nothing(self, window):
        window.main_entry.setText("negligence")
        assert window._syntax_notices[window.main_entry].isVisible() is False

    def test_it_reports_live_as_you_type(self, qtbot, window):
        action = window._syntax_notices[window.main_entry]
        window.main_entry.setFocus()

        qtbot.keyClicks(window.main_entry, "Profit ")
        assert action.isVisible() is False

        qtbot.keyClicks(window.main_entry, "%")
        assert action.isVisible() is True

    def test_the_tooltip_says_what_will_happen(self, window):
        window.main_entry.setText("Profit % margin")
        tooltip = window._syntax_notices[window.main_entry].toolTip()
        assert "no warning" in tooltip

    def test_clicking_repairs_the_whole_field(self, window):
        """One decision, not one per character -- see D3."""
        window.main_entry.setText("R&D, 50% & rising")

        window._syntax_notices[window.main_entry].trigger()

        assert window.main_entry.text() == r"R\&D, 50\% \& rising"

    def test_the_icon_goes_away_once_the_text_is_clean(self, window):
        action = window._syntax_notices[window.main_entry]
        window.main_entry.setText("Profit % margin")

        action.trigger()

        assert action.isVisible() is False

    def test_the_repair_is_undoable_in_the_field(self, window):
        """
        A mechanical correction someone did not want should cost one
        keystroke to reverse, so the fix is written through the field's
        own editing operations rather than setText.
        """
        window.main_entry.setText("Profit % margin")
        window._syntax_notices[window.main_entry].trigger()

        window.main_entry.undo()

        assert window.main_entry.text() == "Profit % margin"

    def test_a_finding_with_no_fix_offers_no_click(self, window):
        window.main_entry.setText(r"\textbf{unclosed")
        action = window._syntax_notices[window.main_entry]

        assert action.isVisible() is True
        assert action.isEnabled() is False

    def test_a_repair_that_cannot_finish_says_so(self, window):
        messages = []
        window.statusMessageRequested.connect(lambda text, _ms: messages.append(text))
        window.main_entry.setText("50% and a stray }")

        window._syntax_notices[window.main_entry].trigger()

        assert window.main_entry.text() == r"50\% and a stray }"
        assert "needs a decision" in messages[-1]

    def test_a_sort_field_is_read_as_a_sort_key(self, window):
        """The same characters break the same way; what goes wrong differs."""
        window.show_sort_keys.setChecked(True)
        sort_field = window.sort_entries[MAIN]
        sort_field.setText("user@host")

        tooltip = window._syntax_notices[sort_field].toolTip()

        assert "this key will be split again" in tooltip

    def test_the_advice_and_the_undo_button_coexist(self, window):
        """
        Both are trailing actions on the same field. An automatic split
        leaves a level that still has something to say about it.
        """
        window.main_entry.setText('user@host@more')
        window.main_entry.editingFinished.emit()

        assert MAIN in window._split_notices
        assert window._syntax_notices[window.main_entry].isVisible() is True


class TestEntryTableAdvice:
    def _populate(self, table, *raw_headings):
        table.populate_entry_modifier_display([
            {"unique_id_number": index, "heading_raw_text": raw}
            for index, raw in enumerate(raw_headings, start=1)
        ])

    def test_a_loaded_entry_is_marked(self, table):
        self._populate(table, "Profit % margin")
        item = table.base_model.item(0, COL_MAIN_DISP)

        assert _has_icon(item)
        assert "no warning" in item.toolTip()

    def test_a_clean_entry_is_left_alone(self, table):
        self._populate(table, r"Widgets@\textbf{Widgets}!Sub|textbf")

        for column in (COL_MAIN_DISP, COL_MAIN_SORT, COL_SUB1_DISP):
            item = table.base_model.item(0, column)
            assert not _has_icon(item)
            assert item.toolTip() == ""

    def test_a_sort_cell_is_read_as_a_sort_key(self, table):
        self._populate(table, "50%@Widgets")
        item = table.base_model.item(0, COL_MAIN_SORT)

        assert _has_icon(item)
        assert "sort key" in item.toolTip()

    def test_an_appended_entry_is_marked_the_same_way(self, table):
        """
        "Creating or editing" was the requirement; the two routes call
        the identical function rather than each having an opinion.
        """
        self._populate(table, "Clean")
        table.append_entry_row({"unique_id_number": 2, "heading_raw_text": "AT&T"})

        item = table.base_model.item(1, COL_MAIN_DISP)
        assert _has_icon(item)

    def test_editing_a_clean_cell_into_a_dirty_one_marks_it(self, table):
        self._populate(table, "Clean entry")
        item = table.base_model.item(0, COL_MAIN_DISP)

        item.setText("R&D")

        assert _has_icon(item)
        assert "reserved in LaTeX" in item.toolTip()

    def test_correcting_a_cell_takes_the_mark_off(self, table):
        self._populate(table, "R&D")
        item = table.base_model.item(0, COL_MAIN_DISP)

        item.setText(r"R\&D")

        assert not _has_icon(item)
        assert item.toolTip() == ""

    def test_the_page_column_is_not_checked(self, table):
        """Its content is a command name chosen from a combo box."""
        self._populate(table, "Widgets|textbf")
        assert not _has_icon(table.base_model.item(0, COL_ENCAP))

    def test_the_table_and_the_window_say_the_same_thing(self, table, window):
        self._populate(table, "Profit % margin")
        window.main_entry.setText("Profit % margin")

        cell_tooltip = table.base_model.item(0, COL_MAIN_DISP).toolTip()
        field_tooltip = window._syntax_notices[window.main_entry].toolTip()

        # The field additionally offers the repair; everything else matches.
        assert cell_tooltip in field_tooltip.replace(
            f"<p><i>{levels._FIX_HINT}</i></p>", ""
        )
