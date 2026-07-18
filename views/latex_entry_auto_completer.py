from PySide6.QtCore import QEvent, QObject, Qt, QStringListModel
from PySide6.QtWidgets import QCompleter, QLineEdit


class TabCompletionEventFilter(QObject):
    def __init__(self, completer: QCompleter, target_field: QLineEdit, parent=None):
        super().__init__(parent)
        self.completer = completer
        self.target_field = target_field

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab:
            popup = self.completer.popup()
            index = popup.currentIndex()

            completion = None
            if index.isValid():
                completion = self.completer.completionModel().data(index)
            elif self.completer.currentCompletion():
                completion = self.completer.currentCompletion()

            if completion:
                self.target_field.blockSignals(True)
                self.target_field.setText(completion)
                self.target_field.blockSignals(False)
                self.target_field.setCursorPosition(len(completion))
                popup.hide()
                self.target_field.setFocus()
                return True

        return super().eventFilter(watched, event)


class LatexEntryAutoCompleter(QObject):
    def __init__(self, field: QLineEdit, completions: list[str], parent=None):
        super().__init__(parent)
        self.field = field
        self.completer = None
        self._popup_filter = None
        self._text_changed_connection = None
        self._build(completions)

    def _build(self, completions: list[str]) -> None:
        model = QStringListModel(completions, self.field)
        self.completer = QCompleter(model, self.field)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)

        self._text_changed_connection = self.field.textChanged.connect(
            lambda text, c=self.completer: c.complete() if len(text) >= 2 else c.popup().hide()
        )

        self.field.setCompleter(self.completer)

        popup = self.completer.popup()
        self._popup_filter = TabCompletionEventFilter(self.completer, self.field, self)
        popup.installEventFilter(self._popup_filter)

    def detach(self) -> None:
        """
        Disconnects this helper's textChanged handler before it's replaced
        (see LatexIndexWindow._attach_completer, called on every project
        (re)load/resync). field.setCompleter() -- called for the
        replacement helper's own completer -- deletes THIS completer
        immediately (it was constructed with field as its parent, and Qt
        auto-deletes the previous completer when a new one is set), but
        that leaves this closure's `c=self.completer` reference dangling
        while the closure itself stays connected to field.textChanged
        (field is never destroyed, only re-attached to). deleteLater()
        alone doesn't help -- it schedules THIS QObject for deletion, but
        the lambda is still live and still connected right up until then,
        and the next keystroke fires it against an already-deleted
        QCompleter ("Internal C++ object ... already deleted").
        """
        if self._text_changed_connection is not None:
            try:
                self.field.textChanged.disconnect(self._text_changed_connection)
            except (RuntimeError, TypeError):
                pass
            self._text_changed_connection = None

    # def _handle_text_changed(self, text: str) -> None:
    #     if len(text) >= 2:
    #         self.completer.complete()
    #     else:
    #         self.completer.popup().hide()

    def add_completion_entry(self, term: str) -> None:
        if not term:
            return

        model = self.completer.model()
        if model is None or not hasattr(model, "stringList"):
            return

        existing = model.stringList()
        if term not in existing:
            model.setStringList(sorted(existing + [term]))