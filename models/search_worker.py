import os
from PySide6.QtCore import QThread, Signal
from rapidfuzz import fuzz

class SearchWorker(QThread):
    """
    PRODUCTION-HARDENED: Database-aware project file scanner.
    Operates over filtered file lists to enforce active tree constraints.
    """
    # Signature: file_name, display_loc, snippet, abs_path, line_num, col_num
    match_found = Signal(str, str, str, str, int, int)
    finished = Signal(int)

    def __init__(self, scoped_file_paths: list, term: str, threshold: int, is_fuzzy: bool = True):
        super().__init__()
        self.scoped_file_paths = scoped_file_paths
        self.term = term.strip()
        self.term_lower = self.term.lower()
        self.threshold = threshold
        self.is_fuzzy = is_fuzzy

    def run(self):
        count = 0
        for file_path in self.scoped_file_paths:
            if not os.path.exists(file_path):
                continue
                
            file_name = os.path.basename(file_path)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line_clean = line.strip()
                        
                        if self.is_fuzzy:
                            # Tab 1: RapidFuzz Levenshtein partial string comparison match 
                            score = fuzz.partial_ratio(self.term_lower, line_clean.lower())
                            is_match = score >= self.threshold
                            score_label = f" (Score: {int(score)})"
                        else:
                            # Tab 2: Exact case-insensitive boundary subphrase lookahead match
                            is_match = self.term_lower in line_clean.lower()
                            score_label = ""

                        if is_match:
                            # Calculate the precise 1-indexed column offset index pointer
                            try:
                                col_idx = line_clean.lower().find(self.term_lower)
                                col_num = (col_idx + 1) if col_idx != -1 else 1
                            except Exception:
                                col_num = 1

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
