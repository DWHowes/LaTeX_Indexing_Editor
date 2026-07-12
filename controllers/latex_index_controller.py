from PySide6.QtCore import QObject
from PySide6.QtGui import QTextCursor

from models.latex_entry_model import IndexEntryModel
from models.latex_entry_model import ReferenceCarrier
from views.latex_index_window import LatexIndexWindow

class LatexIndexController(QObject):
    def __init__(self, view: LatexIndexWindow, tab_widget):
        super().__init__(view)
        self.view = view
        self.tab_widget = tab_widget

        self.doc_io = None

        self.view.insertRequested.connect(self.handle_insert)
        self.view.formatRequested.connect(self.on_format_requested)

    def on_format_requested(self, command: str):
        self.view.format_selected_text(command)

    def set_doc_io(self, doc_io) -> None:
        """Binds the DocumentIOController after construction."""
        self.doc_io = doc_io

    def handle_insert(self):
        editor = self.tab_widget.currentWidget()
        if not editor:
            print("Error: No active editor found for index insertion.")
            return

        entry_data = self.view.get_entry_data()
        entry = IndexEntryModel(**entry_data)

        if not IndexEntryModel.process_field(entry.main):
            print("Error: Main entry field cannot be empty.")
            return

        path_carrier = ReferenceCarrier("Untitled")
        self.view.syncRequested.emit(editor, path_carrier)
        path = str(path_carrier.value)

        if path == "Untitled":
            save_carrier = ReferenceCarrier(False)
            self.view.saveRequested.emit(editor, save_carrier)
            if not save_carrier.value:
                print("Error: Failed to save the document.")
                return
            self.view.syncRequested.emit(editor, path_carrier)
            path = str(path_carrier.value)
            if path == "Untitled":
                print("Error: Document path is still unresolved after save attempt.")
                return

        cursor = editor.textCursor()
        is_range = cursor.hasSelection() and not entry.xref_enabled

        id_carrier = ReferenceCarrier(-1)
        self.view.nextIdRequested.emit(id_carrier)
        assigned_idn = id_carrier.value
        if assigned_idn == -1:
            print("Error: Failed to retrieve a valid unique ID for the new index entry.")
            return

        close_idn = None
        if is_range:
            close_carrier = ReferenceCarrier(-1)
            self.view.nextIdRequested.emit(close_carrier)
            close_idn = close_carrier.value
            if close_idn == -1:
                print("Error: Failed to retrieve closing ID for range entry.")
                return

        self.insert_latex(editor, entry, path, assigned_idn, close_idn)

    def insert_latex(self, editor, entry: IndexEntryModel, path: str, 
                    assigned_id: int, close_id: int | None = None):
        cursor = editor.textCursor()
        chain = entry.chain()
        doc = editor.document()

        if entry.xref_enabled:
            # Single macro — xref entries are never ranges
            absolute_start = cursor.position()
            target_term = entry.xref_target.strip()
            mode = entry.xref_type
            macro_tag = f"\\{entry.command_name}{{{chain}|{mode}{{{target_term}}}}}"
            cursor.insertText(macro_tag)
            absolute_end = cursor.position()
            editor.setTextCursor(cursor)

            block = doc.findBlock(absolute_start)
            true_line = block.blockNumber() + 1
            true_col = absolute_start - block.position()

            uid_dict = entry.metadata(assigned_id, path, true_line, true_col)
            uid_dict["range_partner_id"] = None
            uid_dict["is_range_closer"] = False
            self._attach_byte_coordinates(doc, uid_dict, path, absolute_start, absolute_end)
            self.view.indexInserted.emit(entry.normalized_parts(), uid_dict)

        elif close_id is not None:
            # Range entry — two macros, two records, one logical entry in the views
            selected_text = cursor.selectedText()
            start_format = f"|{entry.page_style}|(" if entry.page_style else "|("
            end_format   = f"|{entry.page_style}|)" if entry.page_style else "|)"
            start_tag = f"\\{entry.command_name}{{{chain}{start_format}}}"
            end_tag   = f"\\{entry.command_name}{{{chain}{end_format}}}"

            # Selection start/end, independent of drag direction. cursor.position()
            # returns the "moving" end of the selection (left-to-right drags land
            # at the right edge, right-to-left drags land at the left edge), so it
            # cannot be used here. selectionStart()/selectionEnd() always return
            # the correct lower/upper bounds regardless of drag direction.
            open_abs_start = cursor.selectionStart()
            selection_end = cursor.selectionEnd()

            # Explicitly select and remove the original selection before inserting.
            # Collapsing via setPosition() alone leaves the selected text in place,
            # which caused it to be duplicated when re-inserted below.
            cursor.setPosition(open_abs_start)
            cursor.setPosition(selection_end, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()

            cursor.insertText(start_tag)
            open_abs_end = cursor.position()

            # Selected text between macros
            cursor.insertText(selected_text)

            # Closing macro
            close_abs_start = cursor.position()
            cursor.insertText(end_tag)
            close_abs_end = cursor.position()

            editor.setTextCursor(cursor)

            # Opening record — visible in views
            open_block = doc.findBlock(open_abs_start)
            open_line = open_block.blockNumber() + 1
            open_col  = open_abs_start - open_block.position()
            open_dict = entry.metadata(assigned_id, path, open_line, open_col)
            open_dict["range_partner_id"] = close_id
            open_dict["is_range_closer"]  = False
            self._attach_byte_coordinates(doc, open_dict, path, open_abs_start, open_abs_end)
            self.view.indexInserted.emit(entry.normalized_parts(), open_dict)

            # Closing record — hidden from views, coordinate record only
            close_block = doc.findBlock(close_abs_start)
            close_line = close_block.blockNumber() + 1
            close_col  = close_abs_start - close_block.position()
            close_dict = entry.metadata(close_id, path, close_line, close_col)
            close_dict["range_partner_id"] = assigned_id
            close_dict["is_range_closer"]  = True
            self._attach_byte_coordinates(doc, close_dict, path, close_abs_start, close_abs_end)
            self.view.indexInserted.emit(entry.normalized_parts(), close_dict)

        else:
            # Standard single macro
            absolute_start = cursor.position()
            macro_tag = (f"\\{entry.command_name}{{{chain}|{entry.page_style}}}"
                        if entry.page_style else f"\\{entry.command_name}{{{chain}}}")
            cursor.insertText(macro_tag)
            absolute_end = cursor.position()
            editor.setTextCursor(cursor)

            block = doc.findBlock(absolute_start)
            true_line = block.blockNumber() + 1
            true_col  = absolute_start - block.position()

            uid_dict = entry.metadata(assigned_id, path, true_line, true_col)
            uid_dict["range_partner_id"] = None
            uid_dict["is_range_closer"]  = False
            self._attach_byte_coordinates(doc, uid_dict, path, absolute_start, absolute_end)
            self.view.indexInserted.emit(entry.normalized_parts(), uid_dict)

        self.view.reset_ui()

    def _attach_byte_coordinates(self, doc, uid_dict: dict, path: str,
                                abs_start: int, abs_end: int) -> None:
        """Converts QTextDocument character offsets to file byte offsets."""
        if self.doc_io is not None:
            block = doc.findBlock(abs_start)
            line = block.blockNumber() + 1
            col  = abs_start - block.position()
            buffer_text = doc.toPlainText()
            byte_start = self.doc_io.compute_byte_offset(path, line, col, buffer_text=buffer_text)
            macro_text = buffer_text[abs_start:abs_end]
            byte_end   = byte_start + len(macro_text.encode('utf-8'))
            uid_dict["absolute_position"] = byte_start
            uid_dict["absolute_end"]      = byte_end
        else:
            print(f"[LATEX INDEX CTRL] doc_io not injected — coordinates unavailable for {path}")
            uid_dict["absolute_position"] = None
            uid_dict["absolute_end"]      = None
