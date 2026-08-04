r"""
The Index Entry window's per-level sort fields.

The window used to have none: a level containing \textbf/\textit had a
sort key manufactured for it by stripping the macros, so
"\textit{The Quality of Mercy}" filed under T and "RMS \textit{Titanic}"
under R. Both are wrong -- an indexer files those under Q and T -- and
neither was visible anywhere before the macro reached the .tex file.

The rules these tests hold:

  * a level's Sort field appears on its own once that level carries
    formatting, and on demand for every level via "Show sort keys";
  * it starts as grammar.suggested_sort_key of the display text and keeps
    following it until the indexer types in it, after which nothing
    rewrites it -- including emptying it;
  * only what is in the field is written; nothing is inferred.
"""
import pytest
from PySide6.QtCore import QSettings

from views.latex_index_window import LatexIndexWindow, SortKeyLineEdit

MAIN, SUB1, SUB2 = 0, 1, 2


@pytest.fixture
def window(qtbot, monkeypatch):
    """A window whose "Show sort keys" preference starts off and goes nowhere."""
    store = {}
    monkeypatch.setattr(QSettings, "value",
                        lambda self, key, default=None, type=None: store.get(key, default))
    monkeypatch.setattr(QSettings, "setValue",
                        lambda self, key, value: store.__setitem__(key, value))

    view = LatexIndexWindow()
    qtbot.addWidget(view)
    view.show()
    return view


def _type(qtbot, field, text):
    """Sets text the way typing does -- textEdited included."""
    field.setFocus()
    field.clear()
    qtbot.keyClicks(field, text)


class TestRevealing:
    def test_a_plain_main_entry_shows_no_sort_field(self, window):
        window.main_entry.setText("negligence")
        assert not window.sort_entries[MAIN].isVisible()

    def test_formatting_reveals_that_level_s_field(self, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")
        assert window.sort_entries[MAIN].isVisible()

    def test_only_the_formatted_level_gets_one(self, window):
        window.main_entry.setText(r"\textit{Die Linke}")
        window.reveal_sub1()
        window.sub1_entry.setText("membership")

        assert window.sort_entries[MAIN].isVisible()
        assert not window.sort_entries[SUB1].isVisible()

    def test_removing_the_formatting_takes_the_field_away_again(self, window):
        window.main_entry.setText(r"\textit{Die Linke}")
        window.main_entry.setText("Die Linke")
        assert not window.sort_entries[MAIN].isVisible()

    def test_the_switch_shows_fields_on_unformatted_levels(self, window):
        window.main_entry.setText("St. John")

        window.show_sort_keys.setChecked(True)

        assert window.sort_entries[MAIN].isVisible()

    def test_the_switch_never_shows_a_field_for_a_hidden_level(self, window):
        """A sort field for a subhead that doesn't exist yet is noise."""
        window.show_sort_keys.setChecked(True)
        assert not window.sort_entries[SUB1].isVisible()

    def test_revealing_a_subhead_brings_its_field_with_it(self, window):
        window.show_sort_keys.setChecked(True)
        window.main_entry.setText("Main")

        window.reveal_sub1()

        assert window.sort_entries[SUB1].isVisible()

    def test_collapsing_a_subhead_clears_and_hides_its_field(self, qtbot, window):
        window.show_sort_keys.setChecked(True)
        window.main_entry.setText("Main")
        window.reveal_sub1()
        _type(qtbot, window.sort_entries[SUB1], "typed")

        window.sub1_entry.setFocus()
        qtbot.keyClick(window.sub1_entry, "\b")

        assert not window.sort_entries[SUB1].isVisible()
        assert window.sort_entries[SUB1].text() == ""
        assert window.sort_entries[SUB1].is_user_owned is False


class TestTheSuggestion:
    def test_it_reads_the_formatting_out(self, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")
        assert window.sort_entries[MAIN].text() == "RMS Titanic"

    def test_it_follows_further_edits(self, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")
        window.main_entry.setText(r"HMS \textit{Titanic}")
        assert window.sort_entries[MAIN].text() == "HMS Titanic"

    def test_an_unformatted_level_suggests_nothing(self, window):
        """
        Echoing the display text back would look like a value that has to
        be there, and means the same as leaving it empty anyway.
        """
        window.show_sort_keys.setChecked(True)
        window.main_entry.setText("St. John")

        assert window.sort_entries[MAIN].text() == ""
        window.show_sort_keys.setChecked(False)

    def test_typing_in_it_takes_ownership(self, qtbot, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")

        _type(qtbot, window.sort_entries[MAIN], "Titanic")

        assert window.sort_entries[MAIN].is_user_owned is True

    def test_an_owned_field_stops_following(self, qtbot, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")
        _type(qtbot, window.sort_entries[MAIN], "Titanic")

        window.main_entry.setText(r"RMS \textit{Titanic} (1912)")

        assert window.sort_entries[MAIN].text() == "Titanic"

    def test_emptying_it_is_respected(self, qtbot, window):
        """
        The whole point of the change: an empty field means "file under the
        display text", and must not quietly refill with a suggestion.
        """
        window.main_entry.setText(r"\textit{Cleared}")
        field = window.sort_entries[MAIN]
        field.setFocus()
        qtbot.keyClicks(field, "x")
        field.clear()
        field.textEdited.emit("")

        window.main_entry.setText(r"\textit{Cleared again}")

        assert field.text() == ""
        assert window.get_sort_keys()[MAIN] == ""


class TestWhatGetsRead:
    def test_get_entry_data_carries_the_keys(self, qtbot, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")
        _type(qtbot, window.sort_entries[MAIN], "Titanic")
        window.reveal_sub1()
        window.sub1_entry.setText("sinking of")

        data = window.get_entry_data()

        assert data["main"] == r"RMS \textit{Titanic}"
        assert data["main_sort"] == "Titanic"
        assert data["sub1_sort"] == ""

    def test_a_hidden_field_reads_as_empty(self, qtbot, window):
        """
        Text left in a field that was hidden again (the formatting was
        removed) must not leak into the tag.
        """
        window.main_entry.setText(r"\textit{Die Linke}")
        _type(qtbot, window.sort_entries[MAIN], "Linke")

        window.main_entry.setText("Die Linke")

        assert window.get_sort_keys()[MAIN] == ""


class TestTypedSortKeySyntax:
    def test_raw_syntax_is_split_into_the_two_fields(self, window):
        """
        Reached by typing makeindex syntax, and by accepting an
        autocomplete suggestion -- the completion lists are built from raw
        heading levels, so they carry whatever key those headings had.
        """
        window.main_entry.setText(r"Titanic@RMS \textit{Titanic}")
        window.main_entry.editingFinished.emit()

        assert window.main_entry.text() == r"RMS \textit{Titanic}"
        assert window.sort_entries[MAIN].text() == "Titanic"
        assert window.sort_entries[MAIN].is_user_owned is True

    def test_it_is_not_split_mid_typing(self, qtbot, window):
        _type(qtbot, window.main_entry, "half@")
        assert window.main_entry.text() == "half@"

    def test_text_with_no_at_is_untouched(self, window):
        window.main_entry.setText("negligence")
        window.main_entry.editingFinished.emit()
        assert window.main_entry.text() == "negligence"


class TestFormattingButtons:
    def test_they_never_target_a_sort_field(self, window):
        window.main_entry.setText(r"\textit{Title}")
        window.main_entry.setFocus()
        sort_field = window.sort_entries[MAIN]
        sort_field.setText("Title")
        sort_field.setFocus()
        sort_field.selectAll()

        window.format_selected_text("textbf")

        assert sort_field.text() == "Title"

    def test_they_grey_out_while_a_sort_field_has_focus(self, window):
        window.main_entry.setText(r"\textit{Title}")
        window.sort_entries[MAIN].setFocus()

        assert window.bold_entry.isEnabled() is False
        assert window.ital_entry.isEnabled() is False

    def test_they_come_back_on_a_display_field(self, window):
        window.main_entry.setText(r"\textit{Title}")
        window.sort_entries[MAIN].setFocus()

        window.main_entry.setFocus()

        assert window.bold_entry.isEnabled() is True


class TestReset:
    def test_insert_clears_the_fields(self, qtbot, window):
        window.main_entry.setText(r"RMS \textit{Titanic}")
        _type(qtbot, window.sort_entries[MAIN], "Titanic")

        window.reset_ui()

        assert window.sort_entries[MAIN].text() == ""
        assert window.sort_entries[MAIN].is_user_owned is False
        assert not window.sort_entries[MAIN].isVisible()

    def test_the_switch_survives_an_insert(self, window):
        """It is how someone works, not part of the entry they just made."""
        window.show_sort_keys.setChecked(True)

        window.reset_ui()

        assert window.show_sort_keys.isChecked() is True

    def test_the_switch_is_remembered(self, window):
        window.show_sort_keys.setChecked(True)

        replacement = LatexIndexWindow()
        try:
            assert replacement.show_sort_keys.isChecked() is True
        finally:
            replacement.deleteLater()


class TestSortKeyLineEdit:
    def test_it_is_the_type_the_window_uses(self, window):
        assert all(isinstance(f, SortKeyLineEdit) for f in window.sort_entries)

    def test_follow_is_a_no_op_once_owned(self):
        field = SortKeyLineEdit()
        field.is_user_owned = True
        field.setText("mine")

        field.follow(r"\textit{something else}")

        assert field.text() == "mine"
