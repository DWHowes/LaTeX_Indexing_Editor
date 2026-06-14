import os
from PySide6.QtCore import QObject, QThread, Signal, Slot
from rapidfuzz import fuzz

class SearchWorker(QObject):
    """
    PRODUCTION-HARDENED: Database-aware project file scanner.
    Operates over filtered file lists to enforce active tree constraints.
    """
    match_found = Signal(str, str, str, str, int, int)
    finished = Signal(int)

    def __init__(self, scoped_file_paths: list, term: str, threshold: int, is_fuzzy: bool = True):
        super().__init__()
        self.scoped_file_paths = scoped_file_paths
        self.term = term.strip()
        self.term_lower = self.term.lower()
        self.threshold = threshold
        self.is_fuzzy = is_fuzzy
        self._is_abort_requested = False

    @Slot()
    def process(self):
        count = 0
        for file_path in self.scoped_file_paths:
            if self._is_abort_requested:
                break
            if not os.path.exists(file_path):
                continue

            file_name = os.path.basename(file_path)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line_num, line in enumerate(f, 1):
                        if self._is_abort_requested:
                            break
                        line_clean = line.strip()

                        if self.is_fuzzy:
                            score = fuzz.token_set_ratio(self.term_lower, line_clean.lower())
                            is_match = score >= self.threshold
                            score_label = f" (Score: {int(score)})"
                            col_num = 1  # column not meaningful for fuzzy matches
                        else:
                            is_match = self.term_lower in line_clean.lower()
                            score_label = ""
                            col_idx = line_clean.lower().find(self.term_lower)
                            col_num = (col_idx + 1) if col_idx != -1 else 1

                        if is_match:
                            display_loc = f"Line {line_num}{score_label}"
                            self.match_found.emit(
                                file_name,
                                display_loc,
                                line_clean,
                                file_path,
                                line_num,
                                col_num
                            )
                            count += 1

            except Exception as read_fault:
                print(f"CRITICAL: Background index scanner bypassed {file_path}: {str(read_fault)}")

        self.finished.emit(count)

    def stop(self):
        self._is_abort_requested = True


class SafeSearchThread(QThread):
    """
    Thread-Isolated Container for SearchWorker.
    Matches SafeProjectLoadThread pattern for consistency.
    """
    match_found = Signal(str, str, str, str, int, int)
    finished = Signal(int)

    def __init__(self, scoped_file_paths: list, term: str, threshold: int, is_fuzzy: bool = True, parent=None):
        super().__init__(parent)
        self.worker = SearchWorker(
            scoped_file_paths=scoped_file_paths,
            term=term,
            threshold=threshold,
            is_fuzzy=is_fuzzy
        )
        self.worker.moveToThread(self)
        self.worker.match_found.connect(self.match_found.emit)
        self.worker.finished.connect(self._handle_thread_cleanup)
        self.started.connect(self.worker.process)

    def _handle_thread_cleanup(self, count: int):
        self.finished.emit(count)
        self.quit()
        self.wait()

    def stop(self):
        self.worker.stop()