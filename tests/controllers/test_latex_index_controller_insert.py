"""
LatexIndexController's core entry-creation path -- handle_insert /
insert_latex / _attach_span_coordinates. This is the app's central
feature (turning the Index Entry panel into a live \\index{...} macro in
the active editor tab) and had zero coverage anywhere in the suite before
this file: every other controller test only ever exercises *existing*
entries (rename/delete/staging), never insertion itself.

Builds a real EditorTab in a real QTabWidget plus the real
LatexIndexWindow view -- both are cheap, side-effect-free Qt widgets, and
a stubbed view/editor pair could easily mask a mismatch between what the
controller assumes about cursor/document behavior and what Qt actually
does (selection direction, block/column arithmetic, etc). A real
DocumentIOController is bound because the controller requires one to
record coordinates at all, but nothing here needs a file on disk.

The coordinates recorded are **character** offsets into the
newline-normalized document text -- the convention every consumer uses
(LatexIndexParser, _rewrite_on_disk's str slicing, _rewrite_in_document's
QTextCursor positions). See TestNonAsciiCoordinates for the regression
that pinned this down.

The three outbound request signals (nextIdRequested / syncRequested /
saveRequested) are normally answered by AppPipelineController; here
they're answered by small inline handlers that mirror that controller's
real semantics (MacroIDGenerator for IDs, editor.get_absolute_path() "or
Untitled" for sync, an always-False save) without pulling in the whole
app object graph.
"""
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTabWidget

from models.macro_id_generator import MacroIDGenerator
from models.session_backup_manager import SessionBackupManager
from models.text_sanitizer import TextSanitizer
from controllers.document_io_controller import DocumentIOController
from controllers.latex_index_controller import LatexIndexController
from views.editor_tab import EditorTab
from views.latex_index_window import LatexIndexWindow


class _InsertRecorder:
    def __init__(self):
        self.calls = []

    def capture(self, parts_list, metadata):
        self.calls.append((list(parts_list), dict(metadata)))


def _build_stack(tmp_path, qtbot, initial_text="Hello world", with_path=True, with_doc_io=True):
    tabs = QTabWidget()
    qtbot.addWidget(tabs)

    editor = EditorTab()
    qtbot.addWidget(editor)
    editor.load_document_content(initial_text)
    if with_path:
        editor.set_absolute_path(str(tmp_path / "chapter.tex"))
    tabs.addTab(editor, "chapter.tex")
    tabs.setCurrentWidget(editor)

    view = LatexIndexWindow(tab_widget=tabs)
    qtbot.addWidget(view)

    controller = LatexIndexController(view, tabs)

    if with_doc_io:
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
        controller.set_doc_io(doc_io)

    id_gen = MacroIDGenerator(starting_id=1)
    view.nextIdRequested.connect(lambda carrier: setattr(carrier, "value", id_gen.get_and_increment_id()))
    view.syncRequested.connect(
        lambda editor_tab, carrier: setattr(carrier, "value", editor_tab.get_absolute_path() or "Untitled")
    )
    view.saveRequested.connect(lambda editor_tab, carrier: setattr(carrier, "value", False))

    recorder = _InsertRecorder()
    view.indexInserted.connect(recorder.capture)

    return controller, view, editor, recorder


def _fill_entry(view, main="", sub1="", sub2="", page_style=None, command_name=None):
    view.main_entry.setText(main)
    view.sub1_entry.setText(sub1)
    view.sub2_entry.setText(sub2)
    if page_style == "bold":
        view.bold_ref.setChecked(True)
    elif page_style == "italic":
        view.italic_ref.setChecked(True)
    else:
        view.none_ref.setChecked(True)
    if command_name:
        idx = view.command_selector.findText(command_name)
        if idx == -1:
            view.command_selector.addItem(command_name)
            idx = view.command_selector.findText(command_name)
        view.command_selector.setCurrentIndex(idx)


def _place_cursor(editor, position):
    cursor = editor.textCursor()
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


def _select(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


class TestSortKeys:
    r"""
    End-to-end proof that what the Sort field holds is what reaches the
    .tex file -- and that nothing reaches it otherwise. Field-level
    behaviour (when the field appears, what it suggests) lives in
    test_index_entry_window_sort_keys.py.
    """

    def test_a_partially_italic_name_files_where_the_indexer_says(self, tmp_path, qtbot):
        """"RMS Titanic" belongs under T, not R."""
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main=r"RMS \textit{Titanic}", sub1="sinking of")
        view.sort_entries[0].setText("Titanic")
        view.sort_entries[0].is_user_owned = True

        controller.handle_insert()

        assert editor.toPlainText() == (
            "Hello" + r"\index{Titanic@RMS \textit{Titanic}!sinking of}" + " world"
        )

    def test_a_wholly_italic_title_files_where_the_indexer_says(self, tmp_path, qtbot):
        """"The Quality of Mercy" belongs under Q, not T."""
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main=r"\textit{The Quality of Mercy}")
        view.sort_entries[0].setText("Quality of Mercy")
        view.sort_entries[0].is_user_owned = True

        controller.handle_insert()

        assert editor.toPlainText() == (
            "Hello" + r"\index{Quality of Mercy@\textit{The Quality of Mercy}}" + " world"
        )

    def test_formatting_alone_no_longer_invents_a_key(self, tmp_path, qtbot):
        """
        The regression this whole change exists for: this used to come out
        as "Die Linke@\\textit{Die Linke}" with nobody having asked.
        """
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main=r"\textit{Die Linke}")
        view.sort_entries[0].clear()
        view.sort_entries[0].is_user_owned = True

        controller.handle_insert()

        assert editor.toPlainText() == "Hello" + r"\index{\textit{Die Linke}}" + " world"

    def test_a_plain_entry_never_gains_a_sort_key(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="negligence", sub1="duty of care")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{negligence!duty of care} world"

    def test_each_level_keeps_its_own_key(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        view.show_sort_keys.setChecked(True)
        _fill_entry(view, main=r"\textit{Mercy}", sub1="St. John")
        view.reveal_sub1()
        for index, key in ((0, "Mercy"), (1, "Saint John")):
            view.sort_entries[index].setText(key)
            view.sort_entries[index].is_user_owned = True

        controller.handle_insert()

        assert editor.toPlainText() == (
            "Hello" + r"\index{Mercy@\textit{Mercy}!Saint John@St. John}" + " world"
        )
        view.show_sort_keys.setChecked(False)

    def test_a_range_carries_the_key_into_both_macros(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 0, 5)
        _fill_entry(view, main=r"RMS \textit{Titanic}")
        view.sort_entries[0].setText("Titanic")
        view.sort_entries[0].is_user_owned = True

        controller.handle_insert()

        body = r"Titanic@RMS \textit{Titanic}"
        assert editor.toPlainText() == (
            "\\index{" + body + "|(}Hello\\index{" + body + "|)} world"
        )

    def test_a_missing_key_on_formatted_text_is_reported_not_blocked(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        messages = []
        view.statusMessageRequested.connect(lambda text, timeout: messages.append(text))
        _fill_entry(view, main=r"\textit{Die Linke}")
        view.sort_entries[0].clear()
        view.sort_entries[0].is_user_owned = True

        controller.handle_insert()

        assert editor.toPlainText() == "Hello" + r"\index{\textit{Die Linke}}" + " world"
        assert len(messages) == 1
        assert "Main" in messages[0]

    def test_nothing_is_reported_for_an_ordinary_entry(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        messages = []
        view.statusMessageRequested.connect(lambda text, timeout: messages.append(text))
        _fill_entry(view, main="negligence")

        controller.handle_insert()

        assert messages == []


class TestStandardInsert:
    def test_inserts_the_macro_at_the_cursor(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)  # right after "Hello"
        _fill_entry(view, main="Main", sub1="Sub")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main!Sub} world"

    def test_emits_indexInserted_with_normalized_parts_and_metadata(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", sub1="Sub")

        controller.handle_insert()

        assert len(recorder.calls) == 1
        parts, metadata = recorder.calls[0]
        assert parts == ["Main", "Sub"]
        assert metadata["id"] == 1
        assert metadata["path"] == editor.get_absolute_path()
        assert metadata["line"] == 1
        assert metadata["col"] == 5
        assert metadata["encap"] == "standard"
        assert metadata["has_references"] is True
        assert metadata["range_partner_id"] is None
        assert metadata["is_range_closer"] is False
        assert metadata["command_name"] == "index"

    def test_recorded_span_matches_the_inserted_macro(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        _parts, metadata = recorder.calls[0]
        macro_text = r"\index{Main}"
        assert metadata["absolute_position"] == 5
        assert metadata["absolute_end"] == 5 + len(macro_text)
        assert editor.toPlainText()[metadata["absolute_position"]:metadata["absolute_end"]] == macro_text

    def test_resets_the_entry_form_after_insert(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", sub1="Sub")

        controller.handle_insert()

        assert view.main_entry.text() == ""
        assert view.sub1_entry.text() == ""
        assert view.sub1_entry.isVisible() is False

    def test_bold_page_style_writes_a_real_latex_command(self, tmp_path, qtbot):
        r"""
        The encap is the command makeindex wraps the page number in, so it
        has to exist: "|bold" compiles to \bold{12} and stops the document
        with an undefined control sequence. The entry table has always
        written textbf; this is the window agreeing with it.
        """
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", page_style="bold")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main|textbf} world"
        assert recorder.calls[0][1]["encap"] == "textbf"

    def test_italic_page_style_writes_a_real_latex_command(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", page_style="italic")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main|textit} world"
        assert recorder.calls[0][1]["encap"] == "textit"

    def test_three_level_chain_uses_bang_separators(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", sub1="Sub1", sub2="Sub2")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main!Sub1!Sub2} world"

    def test_custom_command_name_is_used_for_the_macro_and_metadata(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", command_name="isidx")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\isidx{Main} world"
        assert recorder.calls[0][1]["command_name"] == "isidx"


class TestStyledRange:
    r"""
    A page style on a range is written marker-first, "|(textbf" ...
    "|)textbf" -- the only form makeindex reads as a styled range.

    It used to be written "|style|(", which is not a range to makeindex
    (it takes "(" as a marker only at the *start* of an encap) and not a
    heading to this application either: grammar.split_encap cuts at the
    last "|", so the tag came back as a heading literally containing
    "|textbf". An interim guard then dropped the style and said so in the
    status bar; the grammar now carries both halves, so the style goes in
    and nothing is reported.
    """

    def test_the_style_follows_the_marker_on_both_halves(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        _fill_entry(view, main="Main", page_style="bold")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello \index{Main|(textbf}world\index{Main|)textbf}"

    def test_italic_too(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        _fill_entry(view, main="Main", page_style="italic")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello \index{Main|(textit}world\index{Main|)textit}"

    def test_nothing_is_reported_to_the_status_bar(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        messages = []
        view.statusMessageRequested.connect(lambda text, timeout: messages.append(text))
        _fill_entry(view, main="Main", page_style="bold")

        controller.handle_insert()

        assert messages == []

    def test_the_records_carry_the_marker_and_the_style(self, tmp_path, qtbot):
        """
        IndexEntryModel.metadata reports only the page style -- it never
        knows a range is being inserted -- so insert_latex has to state
        the real encap itself. When it did not, every reader of the
        cached field (the Page column, the range consistency checker) saw
        a freshly inserted range as two unrelated point references, and a
        table edit reassembled the opener's heading without its "|(".
        """
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        _fill_entry(view, main="Main", page_style="bold")

        controller.handle_insert()

        assert [call[1]["encap"] for call in recorder.calls] == ["(textbf", ")textbf"]

    def test_a_plain_range_records_the_bare_markers(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert [call[1]["encap"] for call in recorder.calls] == ["(", ")"]

    def test_a_styled_point_reference_is_untouched(self, tmp_path, qtbot):
        """No marker on a point reference -- the command stands alone."""
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        messages = []
        view.statusMessageRequested.connect(lambda text, timeout: messages.append(text))
        _fill_entry(view, main="Main", page_style="bold")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main|textbf} world"
        assert messages == []


class TestRangeInsert:
    def test_wraps_the_selection_in_open_and_close_macros(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)  # "world"
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello \index{Main|(}world\index{Main|)}"

    def test_emits_two_indexInserted_calls_for_open_and_close(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert len(recorder.calls) == 2
        open_parts, open_meta = recorder.calls[0]
        close_parts, close_meta = recorder.calls[1]
        assert open_parts == ["Main"]
        assert close_parts == ["Main"]

    def test_open_and_close_records_cross_reference_each_other(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _select(editor, 6, 11)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        _open_parts, open_meta = recorder.calls[0]
        _close_parts, close_meta = recorder.calls[1]
        assert open_meta["id"] == 1
        assert close_meta["id"] == 2
        assert open_meta["is_range_closer"] is False
        assert close_meta["is_range_closer"] is True
        assert open_meta["range_partner_id"] == close_meta["id"]
        assert close_meta["range_partner_id"] == open_meta["id"]

    def test_selection_survives_intact_between_the_two_macros(self, tmp_path, qtbot):
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello curious world today")
        start = "Hello ".__len__()
        end = start + "curious world".__len__()
        _select(editor, start, end)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert r"\index{Main|(}curious world\index{Main|)}" in editor.toPlainText()

    def test_right_to_left_drag_selection_still_wraps_correctly(self, tmp_path, qtbot):
        """
        cursor.position() lands at the LEFT edge for a right-to-left drag,
        which is exactly the bug selectionStart()/selectionEnd() guard
        against (see the comment in insert_latex). Build the selection with
        the anchor on the right to simulate that drag direction.
        """
        controller, view, editor, _recorder = _build_stack(tmp_path, qtbot, "Hello world")
        cursor = editor.textCursor()
        cursor.setPosition(11)  # end of "world"
        cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)  # drag back to start of "world"
        editor.setTextCursor(cursor)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello \index{Main|(}world\index{Main|)}"


class TestInsertAborts:
    def test_empty_main_field_does_not_insert_or_emit(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="   ")

        controller.handle_insert()

        assert editor.toPlainText() == "Hello world"
        assert recorder.calls == []

    def test_untitled_document_that_fails_to_save_does_not_insert_or_emit(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world", with_path=False)
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert editor.toPlainText() == "Hello world"
        assert recorder.calls == []

    def test_no_active_editor_does_not_raise(self, tmp_path, qtbot):
        controller, view, _editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        controller.tab_widget = QTabWidget()  # empty tab widget: currentWidget() is None
        qtbot.addWidget(controller.tab_widget)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert recorder.calls == []


class TestMissingDocIo:
    def test_insert_still_happens_but_coordinates_are_none(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world", with_doc_io=False)
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main} world"
        _parts, metadata = recorder.calls[0]
        assert metadata["absolute_position"] is None
        assert metadata["absolute_end"] is None


class TestNonAsciiCoordinates:
    r"""
    Regression: this path used to convert the cursor's character offsets
    into UTF-8 *byte* offsets before recording them, while every consumer
    of absolute_position/absolute_end works in characters
    (LatexIndexParser.parse_file emits match.start() into a str;
    DocumentIOController._rewrite_on_disk slices content[pos:end] on a str;
    _rewrite_in_document calls QTextCursor.setPosition). The two agree
    only while the text before the macro is pure ASCII -- one accented
    character earlier in the file skewed the stored span by one byte per
    non-ASCII character.

    The consequence was silent: rewrite_macro_span's "does this span look
    like a macro" guard rejected the misaligned slice and aborted, so
    editing or deleting such an entry did nothing at all, and the bad
    coordinates persisted in the DB across reopens (project load trusts
    the DB) until a manual resync.

    Line endings were never part of this -- both producer and consumer
    normalize CRLF to LF -- so these cases vary only the encoding.
    """

    def test_accented_text_before_the_macro_does_not_skew_the_span(self, tmp_path, qtbot):
        body = "Caf\u00e9 Ren\u00e9. "  # two non-ASCII chars, two UTF-8 bytes each
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, body + "tail")
        _place_cursor(editor, len(body))
        _fill_entry(view, main="Main")

        controller.handle_insert()

        _parts, metadata = recorder.calls[0]
        macro_text = r"\index{Main}"
        assert metadata["absolute_position"] == len(body)
        assert metadata["absolute_end"] == len(body) + len(macro_text)
        # The real contract: the recorded span must slice back to the macro
        # out of the same text DocumentIOController would be working with.
        text = editor.toPlainText()
        assert text[metadata["absolute_position"]:metadata["absolute_end"]] == macro_text

    def test_the_recorded_span_survives_a_real_rewrite(self, tmp_path, qtbot):
        """
        End-to-end proof that the units line up: feed the recorded
        coordinates straight back into rewrite_macro_span (the consumer
        that used to silently abort here) and require the rewrite to land.
        """
        body = "\u00c5ngstr\u00f6m and M\u00fcller. "
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, body + "tail")
        _place_cursor(editor, len(body))
        _fill_entry(view, main="Main")
        controller.handle_insert()
        _parts, metadata = recorder.calls[0]

        delta = controller.doc_io.rewrite_macro_span(
            editor.get_absolute_path(),
            metadata["absolute_position"],
            metadata["absolute_end"],
            r"\index{Renamed}",
        )

        assert delta is not None, "rewrite_macro_span rejected the recorded span"
        assert r"\index{Renamed}" in editor.toPlainText()

    def test_range_entry_spans_are_also_character_offsets(self, tmp_path, qtbot):
        body = "Se\u00f1or. "
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, body + "selected tail")
        cursor = editor.textCursor()
        cursor.setPosition(len(body))
        cursor.setPosition(len(body) + 8, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        _fill_entry(view, main="Main")

        controller.handle_insert()

        text = editor.toPlainText()
        opener = recorder.calls[0][1]
        closer = recorder.calls[1][1]
        assert text[opener["absolute_position"]:opener["absolute_end"]] == r"\index{Main|(}"
        assert text[closer["absolute_position"]:closer["absolute_end"]] == r"\index{Main|)}"
