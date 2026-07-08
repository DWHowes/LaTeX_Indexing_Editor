# entry_modifier_table_view.py (new file)
from PySide6.QtWidgets import QTableView, QAbstractItemDelegate
from PySide6.QtCore import Signal


class EntryModifierTableView(QTableView):
    """
    QTableView subclass for the entry modifier table.
    Adds edit_completed_no_next_row signal to catch the cases where Qt's
    closeEditor hint gives EntryModifierController no natural "row changed"
    event to hook a row-finalize onto -- currentRowChanged won't fire in
    either of these:

    - Tab pressed on the last editable cell, with nowhere to advance to
      (hint is EditNextItem, but the current row doesn't change).
    - Enter/Return pressed at all. Qt does NOT report Enter as EditNextItem --
      QStyledItemDelegate's editor event filter reports it as
      SubmitModelCache, a distinct EndEditHint that never carries row-advance
      semantics, on the last row or any other. Missing this case meant every
      edit committed with Enter updated the model (the cell visibly showed
      the new text) but never fired EntryModifierController
      ._finalize_row_edit, so the edit stayed staged indefinitely -- never
      written to the .tex file or reconciled against the tree -- until the
      user separately moved to a different row by some other means (a
      click, or Tab all the way off the row).
    """
    edit_completed_no_next_row = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def closeEditor(self, editor, hint):
        row_before = self.currentIndex().row()
        super().closeEditor(editor, hint)

        if hint == QAbstractItemDelegate.EndEditHint.SubmitModelCache:
            # Enter/Return. Qt never advances the current row for this
            # hint, so there is no other event to hang the row-finalize
            # on here -- fire it directly.
            self.edit_completed_no_next_row.emit(row_before)
            return

        if hint == QAbstractItemDelegate.EndEditHint.EditNextItem:
            row_after = self.currentIndex().row()
            if row_after == row_before:
                self.edit_completed_no_next_row.emit(row_before)
