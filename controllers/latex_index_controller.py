from PySide6.QtCore import QObject

from models.latex_entry_model import IndexEntryModel
from models.latex_entry_model import ReferenceCarrier
from views.latex_index_window import LatexIndexWindow

class LatexIndexController(QObject):
    def __init__(self, view: LatexIndexWindow, tab_widget):
        super().__init__(view)
        self.view = view
        self.tab_widget = tab_widget

        self.view.insertRequested.connect(self.handle_insert)
        self.view.formatRequested.connect(self.on_format_requested)

    def on_format_requested(self, command: str):
        self.view.format_selected_text(command)

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

        id_carrier = ReferenceCarrier(-1)
        self.view.nextIdRequested.emit(id_carrier)
        assigned_idn = id_carrier.value
        if assigned_idn == -1:
            print("Error: Failed to retrieve a valid unique ID for the new index entry.")
            return

        cursor = editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1

        self.insert_latex(editor, entry, path, assigned_idn, line, col)

    def insert_latex(self, editor, entry: IndexEntryModel, path: str, assigned_id: int):
            cursor = editor.textCursor()
            chain = entry.chain()

            absolute_start = cursor.position()

            if entry.xref_enabled:
                target_term = entry.xref_target.strip()
                mode = entry.xref_type
                macro_tag = f"\\index{{{chain}|{mode}{{{target_term}}}}}"
                cursor.insertText(macro_tag)
            else:
                if cursor.hasSelection():
                    selected_text = cursor.selectedText()
                    start_format = f"|{entry.page_style}|(" if entry.page_style else "|("
                    end_format = f"|{entry.page_style}|)" if entry.page_style else "|)"
                    start_tag = f"\\index{{{chain}{start_format}}}"
                    end_tag = f"\\index{{{chain}{end_format}}}"
                    cursor.insertText(f"{start_tag}{selected_text}{end_tag}")
                else:
                    macro_tag = f"\\index{{{chain}|{entry.page_style}}}" if entry.page_style else f"\\index{{{chain}}}"
                    cursor.insertText(macro_tag)

            absolute_end = cursor.position()
            editor.setTextCursor(cursor)

            # Recompute line/col from absolute_start — authoritative regardless of
            # where the caret was when the Insert button was clicked
            doc = editor.document()
            block = doc.findBlock(absolute_start)
            true_line = block.blockNumber() + 1
            true_col = absolute_start - block.position() + 1

            uid_dict = entry.metadata(assigned_id, path, true_line, true_col)
            uid_dict["absolute_position"] = absolute_start
            uid_dict["absolute_end"] = absolute_end

            self.view.indexInserted.emit(entry.normalized_parts(), uid_dict)
            self.view.reset_ui()
