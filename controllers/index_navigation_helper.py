import re
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from views.editor_tab import EditorTab


class IndexNavigationHelper(QObject):
    """
    Reusable navigation service.
    Owns the file-focus and deferred text-jump logic extracted from
    WorkspaceLifecycleController so that any controller (index tree,
    entry modifier, etc.) can trigger coordinated navigation without
    coupling to workspace internals.
    """

    def __init__(
        self,
        tabs,                        # QTabWidget managed by the workspace
        text_sanitizer,              # Sanitizer instance owned by workspace
        file_watcher,                # FileWatcher instance (may be None)
        open_file_callable,          # WorkspaceLifecycleController.open_file_by_path
        parent: QObject = None,
    ):
        super().__init__(parent)
        self._tabs = tabs
        self._sanitizer = text_sanitizer
        self._file_watcher = file_watcher
        self._open_file = open_file_callable  # Delegate; keeps create_editor_tab in place

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def navigate(
        self,
        path: str,
        line: int,
        col: int,
        fallback: str = "",
        highlight_full_line: bool = False,
        absolute_position: int | None = None,
        absolute_end: int | None = None,
        macro_command: str = "index",
    ) -> None:
        """
        Opens (or focuses) the file at path, then jumps to line/col.
        fallback is a raw macro string used for fuzzy matching if the
        coordinate lands outside the current document block count.
        highlight_full_line: select the entire target line instead of
        detecting/highlighting an \\index{...} macro boundary -- set this for
        navigation sources (e.g. Advanced Search) whose coordinates point at
        arbitrary prose rather than the start of an index macro.

        absolute_position/absolute_end, when known, let EditorTab select the
        exact stored macro span instead of re-detecting its boundary from
        line/col text -- required for entries created with a custom
        indexing command (macro_command), since boundary re-detection only
        ever recognizes literal \\index unless macro_command is also passed
        through for that fallback path.
        """
        if not path:
            return

        active_tab = self._open_file(path)
        if not active_tab:
            return

        QTimer.singleShot(0, lambda: self._execute_deferred_text_jump(
            editor=active_tab,
            line_num=line,
            col_offset=col,
            fallback_search_tag=fallback,
            highlight_full_line=highlight_full_line,
            absolute_position=absolute_position,
            absolute_end=absolute_end,
            macro_command=macro_command,
        ))

    # ------------------------------------------------------------------
    # Private implementation
    # ------------------------------------------------------------------

    def _execute_deferred_text_jump(
        self,
        editor: EditorTab,
        line_num: int,
        col_offset: int,
        fallback_search_tag: str,
        highlight_full_line: bool = False,
        absolute_position: int | None = None,
        absolute_end: int | None = None,
        macro_command: str = "index",
    ) -> None:
        if not isinstance(editor, EditorTab):
            return

        document = editor.document()
        if not document or document.blockCount() == 0:
            return

        resolved_line = max(1, int(line_num))
        resolved_col  = max(1, int(col_offset))
        zero_line     = resolved_line - 1
        total_blocks  = document.blockCount()

        if zero_line < total_blocks:
            block = document.findBlockByNumber(zero_line)
            if block.isValid():
                editor.jump_to_coordinates(
                    line=resolved_line,
                    column=resolved_col,
                    absolute_position=absolute_position,
                    is_one_indexed=True,
                    is_index_jump=True,
                    absolute_end=absolute_end,
                    highlight_full_line=highlight_full_line,
                    macro_command=macro_command,
                )
                return

        if not fallback_search_tag:
            return

        full_text = document.toPlainText()
        matches   = list(re.finditer(re.escape(fallback_search_tag), full_text))
        if not matches:
            return

        anchor_block  = document.findBlockByLineNumber(
            max(0, min(zero_line, total_blocks - 1))
        )
        anchor_offset = anchor_block.position() if anchor_block.isValid() else 0
        best_match    = min(matches, key=lambda m: abs(m.start() - anchor_offset))

        match_block = document.findBlock(best_match.start())
        if not match_block.isValid():
            return

        fallback_line = match_block.blockNumber() + 1
        fallback_col  = (best_match.start() - match_block.position()) + 1

        editor.jump_to_coordinates(
            line=fallback_line,
            column=fallback_col,
            absolute_position=None,
            is_one_indexed=True,
            is_index_jump=True,
            highlight_full_line=highlight_full_line,
            macro_command=macro_command,
        )