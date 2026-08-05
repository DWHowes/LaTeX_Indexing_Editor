r"""
Two things the Index Entry window used to do to entry text in silence.

**The formatting buttons were brace-blind.** They took the line edit's
raw selection offsets literally, and a line edit will happily let someone
select any two positions at all. Selecting just the backslash of
``RMS \textit{Titanic}`` and pressing B wrote
``RMS \textbf{\}textit{Titanic}``; selecting from just after that
backslash into the middle of the word wrote
``RMS \\textbf{textit{Tit}anic}``, where ``\\`` is a line break and
"textit" prints as an ordinary word. Neither stops a build -- they reach
the printed index looking like damage rather than like an error.

**A typed "@" was moved without saying so.** ``user@host`` became
``\index{host}``, filed under "user", with nothing on screen to say it
had happened. The split is right far more often than it is wrong -- it is
how an autocomplete suggestion carrying a sort key gets unpacked -- so it
still happens; it just says so now, and offers to put it back.
"""
import pytest
from PySide6.QtCore import QSettings

from views.latex_index_window import LatexIndexWindow

MAIN, SUB1, SUB2 = 0, 1, 2


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
def messages(window):
    """Everything the window asked the status bar to show."""
    captured = []
    window.statusMessageRequested.connect(lambda text, _ms: captured.append(text))
    return captured


def _format(window, text, start, end, command="textbf"):
    window.main_entry.setText(text)
    window.main_entry.setFocus()
    window.last_focused_field = window.main_entry
    window.main_entry.setSelection(start, end - start)
    window.format_selected_text(command)
    return window.main_entry.text()


class TestFormattingASelection:
    TEXT = r"RMS \textit{Titanic}"

    def test_a_plain_selection_is_wrapped_as_asked(self, window):
        assert _format(window, self.TEXT, 0, 3) == r"\textbf{RMS} \textit{Titanic}"

    def test_selecting_only_a_backslash_no_longer_splits_the_macro(self, window):
        assert _format(window, self.TEXT, 4, 5) == r"RMS \textbf{\textit{Titanic}}"

    def test_selecting_across_the_opening_brace_no_longer_doubles_it(self, window):
        assert _format(window, self.TEXT, 5, 15) == r"RMS \textbf{\textit{Titanic}}"

    def test_the_words_inside_a_group_can_still_be_formatted_alone(self, window):
        assert _format(window, self.TEXT, 12, 19) == r"RMS \textit{\textbf{Titanic}}"

    def test_widening_is_reported_rather_than_done_quietly(self, window, messages):
        _format(window, self.TEXT, 4, 5)
        assert len(messages) == 1
        assert "widened" in messages[0]

    def test_an_untouched_selection_says_nothing(self, window, messages):
        _format(window, self.TEXT, 0, 3)
        assert messages == []

    def test_the_wrapped_run_is_left_selected(self, window):
        _format(window, self.TEXT, 0, 3)
        assert window.main_entry.selectedText() == r"\textbf{RMS}"

    def test_an_unmatched_brace_is_declined_outright(self, window, messages):
        """
        Wrapping would nest a good group inside a broken one and bury the
        real problem. The field is left exactly as it was.
        """
        assert _format(window, r"\textbf{unclosed", 8, 16) == r"\textbf{unclosed"
        assert "unmatched brace" in messages[0]

    def test_it_still_ignores_an_empty_selection(self, window):
        window.main_entry.setText("negligence")
        window.last_focused_field = window.main_entry
        window.main_entry.deselect()

        window.format_selected_text("textbf")

        assert window.main_entry.text() == "negligence"


class TestSortKeySplitNotice:
    def test_the_split_still_happens(self, window):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        assert window.main_entry.text() == "host"
        assert window.sort_entries[MAIN].text() == "user"

    def test_it_is_reported_in_the_status_bar(self, window, messages):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        assert len(messages) == 1
        assert "Main" in messages[0]

    def test_the_level_is_named(self, window, messages):
        window.reveal_sub1()
        window.sub1_entry.setText("user@host")
        window.sub1_entry.editingFinished.emit()

        assert "Subhead 1" in messages[0]

    def test_the_field_carries_a_one_click_undo(self, window):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        assert MAIN in window._split_notices
        assert window._split_notices[MAIN] in window.main_entry.actions()
        assert "user@host" in window._split_notices[MAIN].toolTip()

    def test_undoing_restores_the_text_exactly_as_typed(self, window):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        window._split_notices[MAIN].trigger()

        assert window.main_entry.text() == "user@host"

    def test_undoing_puts_the_sort_field_back_as_it_was(self, window):
        """
        Empty and still following its display text -- a level reading
        "user@host" suggests nothing to file under, so that is the state
        before the split, not merely a cleared field.
        """
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        window._split_notices[MAIN].trigger()

        assert window.sort_entries[MAIN].text() == ""
        assert window.sort_entries[MAIN].is_user_owned is False

    def test_undoing_takes_the_notice_away(self, window):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        undo = window._split_notices[MAIN]
        undo.trigger()

        assert window._split_notices == {}
        assert undo not in window.main_entry.actions()

    def test_leaving_the_field_again_does_not_re_split_it(self, window):
        """
        Otherwise the undo would be undone by the next focus change, which
        is exactly the click that reaches for it.
        """
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()
        window._split_notices[MAIN].trigger()

        window.main_entry.editingFinished.emit()

        assert window.main_entry.text() == "user@host"
        assert window.sort_entries[MAIN].text() == ""

    def test_declining_is_remembered_against_the_text_not_the_field(self, window):
        """Different text in the same field splits as usual."""
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()
        window._split_notices[MAIN].trigger()

        window.main_entry.setText(r"Titanic@RMS \textit{Titanic}")
        window.main_entry.editingFinished.emit()

        assert window.main_entry.text() == r"RMS \textit{Titanic}"
        assert window.sort_entries[MAIN].text() == "Titanic"

    def test_typing_clears_a_stale_notice(self, qtbot, window):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()

        window.main_entry.setFocus()
        qtbot.keyClicks(window.main_entry, "s")

        assert window._split_notices == {}

    def test_text_with_no_at_sign_gets_no_notice(self, window, messages):
        window.main_entry.setText("negligence")
        window.main_entry.editingFinished.emit()

        assert window._split_notices == {}
        assert messages == []

    def test_an_insert_clears_the_notice_and_the_memory(self, window):
        window.main_entry.setText("user@host")
        window.main_entry.editingFinished.emit()
        undo = window._split_notices[MAIN]

        window.reset_ui()

        assert window._split_notices == {}
        assert window._declined_splits == {}
        assert undo not in window.main_entry.actions()
