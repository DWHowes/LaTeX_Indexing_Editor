"""
LatexIndexController's core entry-creation path -- handle_insert /
insert_latex / _attach_byte_coordinates. This is the app's central
feature (turning the Index Entry panel into a live \\index{...} macro in
the active editor tab) and had zero coverage anywhere in the suite before
this file: every other controller test only ever exercises *existing*
entries (rename/delete/staging), never insertion itself.

Builds a real EditorTab in a real QTabWidget plus the real
LatexIndexWindow view -- both are cheap, side-effect-free Qt widgets, and
a stubbed view/editor pair could easily mask a mismatch between what the
controller assumes about cursor/document behavior and what Qt actually
does (selection direction, block/column arithmetic, etc). A real
DocumentIOController is used for the byte-offset math, but its
compute_byte_offset call is fed the live in-memory buffer_text (exactly
as the controller does), so no file ever needs to exist on disk.

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

    def test_byte_offsets_match_the_inserted_macro_span(self, tmp_path, qtbot):
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

    def test_bold_page_style_produces_pipe_bold_suffix_and_encap(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", page_style="bold")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main|bold} world"
        assert recorder.calls[0][1]["encap"] == "bold"

    def test_italic_page_style_produces_pipe_italic_suffix_and_encap(self, tmp_path, qtbot):
        controller, view, editor, recorder = _build_stack(tmp_path, qtbot, "Hello world")
        _place_cursor(editor, 5)
        _fill_entry(view, main="Main", page_style="italic")

        controller.handle_insert()

        assert editor.toPlainText() == r"Hello\index{Main|italic} world"
        assert recorder.calls[0][1]["encap"] == "italic"

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
