r"""
How the index tree orders its nodes.

``CaseInsensitiveItem.sort_key`` answers "what does this heading file
under", which is two questions in one: does it carry an explicit sort
override, and what do its words read as once formatting is read through.
Both were answered here by hand until extraction phase 4a; both are the
dialect's to answer, and doing it by hand had shipped a bug.
"""

from views.index_tree_view import CaseInsensitiveItem


def _key(text: str) -> str:
    return CaseInsensitiveItem(text).sort_key


class TestTheSortKeyReadsThroughFormatting:
    def test_a_plain_heading_files_under_itself(self):
        assert _key("Kant, Immanuel") == "kant, immanuel"

    def test_emphasis_does_not_affect_filing(self):
        r"""
        ``RMS \textit{Titanic}`` files under the words, not under the macro
        name -- otherwise every emphasised term in the index collects under
        T for ``\textit``.
        """
        assert _key(r"RMS \textit{Titanic}") == "rms titanic"

    def test_an_explicit_override_wins(self):
        assert _key(r"kant@\textbf{Kant}") == "kant"


class TestTheBraceBug:
    r"""
    The sort key used to be ``text.split('@')[0]``, which is the naive split
    ``index_tag_grammar`` was written to end. For a heading of ``a{b@c}d``
    that returns ``a{b`` — so a term whose *display* contains a braced macro
    with an ``@`` in it sorted under a fragment of its own markup.

    Nothing in the tree noticed, because a wrong sort order looks like an
    opinion rather than a fault.
    """

    def test_an_at_sign_inside_braces_is_not_a_sort_override(self):
        assert _key("a{b@c}d") == "a{b@c}d".lower()

    def test_a_bare_at_sign_really_does_split_and_that_is_correct(self):
        """
        The counterpart, and the reason the fix above is narrow rather than
        "stop splitting on @". In makeindex an unbraced ``@`` *is* the sort
        separator, so ``user@example.com`` genuinely means "file under
        'user', print 'example.com'" — surprising to an indexer typing an
        address, but the format's rule and not this tree's to overrule.

        The application says so where it belongs: the syntax checker flags a
        bare ``@`` and offers the quote that escapes it.
        """
        assert _key("user@example.com") == "user"


class TestCrossReferenceNodesSortFirst:
    def test_a_see_also_node_sorts_before_ordinary_siblings(self):
        """
        The leading NUL is deliberate and predates this change: a *see also*
        belongs at the head of its sibling run, not alphabetically among
        them.
        """
        see_also = CaseInsensitiveItem("See also Hume", is_see_also=True)
        see_also.is_see_also = True

        assert see_also.sort_key.startswith("\x00")
        assert see_also.sort_key < _key("Aardvark")
