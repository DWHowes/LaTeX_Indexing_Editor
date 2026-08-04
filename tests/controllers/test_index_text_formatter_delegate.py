r"""
IndexTextFormatterDelegate's segmentation of a column-0 string into styled
chunks -- the step that decides which parts of an index term are painted
bold or italic.

The cross-reference case is the reason ITALIC_PREFIX_LENGTH_ROLE exists:
"See"/"See also" is a label this application adds and styles, while the
target after it is a real index term whose appearance is dictated by its
own \index entry. Italicising the whole node (which is what a font on the
item does) silently overrides the target's formatting.
"""
from PySide6.QtGui import QStandardItem, QStandardItemModel

from views.index_text_formatter_delegate import IndexTextFormatterDelegate

ROLE = IndexTextFormatterDelegate.ITALIC_PREFIX_LENGTH_ROLE


def _segments(text, prefix_length=None):
    """The delegate's styled chunks for a cell holding `text`."""
    delegate = IndexTextFormatterDelegate()
    model = QStandardItemModel()
    item = QStandardItem(text)
    if prefix_length is not None:
        item.setData(prefix_length, ROLE)
    model.appendRow(item)
    return delegate._segments_for_index(model.index(0, 0), text)


class TestPlainTerms:
    def test_text_with_no_macros_is_one_unstyled_chunk(self, qtbot):
        assert _segments("Widgets") == [("Widgets", False, False)]

    def test_a_macro_styles_only_its_own_chunk(self, qtbot):
        assert _segments(r"the \textit{Belgrano} sinking") == [
            ("the ", False, False),
            ("Belgrano", True, False),
            (" sinking", False, False),
        ]

    def test_a_sort_key_is_stripped(self, qtbot):
        assert _segments(r"Linke@\textbf{Die Linke}") == [("Die Linke", False, True)]


class TestCrossReferenceLabel:
    def test_the_label_is_italic_and_the_target_is_not(self, qtbot):
        assert _segments("See Gadgets", len("See")) == [
            ("See", True, False),
            (" Gadgets", False, False),
        ]

    def test_a_two_word_label_is_covered_in_full(self, qtbot):
        assert _segments("See also Gizmos", len("See also")) == [
            ("See also", True, False),
            (" Gizmos", False, False),
        ]

    def test_the_target_keeps_the_formatting_its_own_entry_asks_for(self, qtbot):
        r"""The italic here is the target's \textit{}, not the label's."""
        assert _segments(r"See \textit{Die Linke} (Germany)", len("See")) == [
            ("See", True, False),
            (" ", False, False),
            ("Die Linke", True, False),
            (" (Germany)", False, False),
        ]

    def test_a_bold_target_stays_bold_and_upright(self, qtbot):
        assert _segments(r"See also \textbf{Gizmos}", len("See also")) == [
            ("See also", True, False),
            (" ", False, False),
            ("Gizmos", False, True),
        ]

    def test_the_remainder_is_not_split_at_a_literal_at_sign(self, qtbot):
        """
        The model resolves the sort key when it builds the label, so a
        second strip here could only eat a genuine '@' -- and would take
        the label with it.
        """
        assert _segments("See name@domain", len("See")) == [
            ("See", True, False),
            (" name@domain", False, False),
        ]

    def test_a_zero_length_prefix_falls_back_to_plain_parsing(self, qtbot):
        assert _segments("Widgets", 0) == [("Widgets", False, False)]

    def test_a_prefix_longer_than_the_text_does_not_raise(self, qtbot):
        assert _segments("See", 40) == [("See", True, False)]


class TestCache:
    def test_the_same_string_caches_separately_per_strip_setting(self, qtbot):
        """
        Both readings of "See a@b" are reachable in one session; sharing a
        cache entry would hand one of them the other's segments.
        """
        delegate = IndexTextFormatterDelegate()

        stripped = delegate._parse_latex_formatting_segments("See a@b")
        kept = delegate._parse_latex_formatting_segments("See a@b", strip_sort_key=False)

        assert stripped == [("b", False, False)]
        assert kept == [("See a@b", False, False)]

    def test_clearing_the_cache_leaves_it_usable(self, qtbot):
        delegate = IndexTextFormatterDelegate()
        delegate._parse_latex_formatting_segments("Widgets")

        delegate.clear_cache()

        assert delegate._parse_latex_formatting_segments("Widgets") == [
            ("Widgets", False, False)
        ]
