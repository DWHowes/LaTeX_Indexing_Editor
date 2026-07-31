"""
views.entry_modifier_list.set_encap_style_values -- the bold/italic encap
name lists behind the Entry Table's Page column, which became a user
preference (Preferences -> General) because a project styling page numbers
with its own macro silently got a plain, mis-styled cell for it.

Module-level state, so every test restores the defaults afterwards -- these
lists are read by a free function called while building every table row,
and a leaked value would change how an unrelated test renders.
"""
import pytest

from views import entry_modifier_list as eml


@pytest.fixture(autouse=True)
def _restore_defaults():
    yield
    eml.set_encap_style_values(
        list(eml.DEFAULT_BOLD_ENCAP_VALUES),
        list(eml.DEFAULT_ITALIC_ENCAP_VALUES),
    )


class TestSetEncapStyleValues:
    def test_defaults_are_recognised_out_of_the_box(self):
        assert eml._is_bold_encap("textbf") is True
        assert eml._is_italic_encap("it") is True

    def test_a_custom_bold_name_is_recognised_after_being_set(self):
        eml.set_encap_style_values(["strong"], None)

        assert eml._is_bold_encap("strong") is True

    def test_setting_bold_replaces_rather_than_extends(self):
        """
        The field shows the full list, so what the user leaves in it IS the
        list -- a name they deleted has to stop being recognised.
        """
        eml.set_encap_style_values(["strong"], None)

        assert eml._is_bold_encap("textbf") is False

    def test_passing_none_leaves_that_list_untouched(self):
        eml.set_encap_style_values(["strong"], None)

        assert eml._is_italic_encap("textit") is True

    def test_an_empty_list_leaves_the_current_values_alone(self):
        """
        An empty preferences field means "I didn't set this", never
        "recognise nothing" -- the latter would silently switch bold and
        italic rendering off altogether.
        """
        eml.set_encap_style_values([], [])

        assert eml._is_bold_encap("bold") is True
        assert eml._is_italic_encap("italic") is True

    def test_values_are_normalised_the_way_they_are_compared(self):
        """Entered as ' TextBF ', matched against a 'textbf' encap."""
        eml.set_encap_style_values([" TextBF ", "STRONG"], None)

        assert eml._is_bold_encap("textbf") is True
        assert eml._is_bold_encap("strong") is True

    def test_a_comma_separated_string_is_accepted(self):
        """What QSettings hands back when the list round-trips as a string."""
        eml.set_encap_style_values("strong, heavy", "slanted")

        assert eml._is_bold_encap("heavy") is True
        assert eml._is_italic_encap("slanted") is True

    def test_blank_entries_between_commas_are_dropped(self):
        eml.set_encap_style_values("strong,,  ,heavy", None)

        assert eml._is_bold_encap("strong") is True
        assert eml._is_bold_encap("") is False

    def test_a_custom_bold_encap_renders_the_cell_bold(self):
        """The behaviour the preference actually exists for."""
        eml.set_encap_style_values(["strong"], None)

        item = eml._make_encap_item("strong")

        assert item.font().bold() is True

    def test_a_default_range_marker_stays_non_editable(self):
        """
        Range openers/closers are structural, not a page style. Nothing in
        the preference touches that, and this pins it so a future change
        to the encap lists can't quietly make one editable.
        """
        from PySide6.QtCore import Qt

        item = eml._make_encap_item("(")

        assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)
