import os
import re

class IndexTreeModelEngine:
    """
    Business Logic & Data Model.
    Tracks staged changes and parses raw LaTeX strings.
    Strict MVC: 100% decoupled from PySide6 widgets, fonts, and views.
    """
    def __init__(self, repository_model):
        self.repo = repository_model  # Database repository layer
        self._staged_db_entries: list = []
        self._cross_reference_cache: dict = {}        

    def has_unsaved_changes(self) -> bool:
        return len(self._staged_db_entries) > 0

    def clear_staged_entries(self):
        self._staged_db_entries.clear()


    def reset_transaction_arrays(self) -> None:
        """
        Purges all volatile transactional staging arrays from memory.
        Ensures a completely fresh tracking state for new project loads.
        """
        self._staged_db_entries.clear()
        self._cross_reference_cache.clear()

    def commit_staged_changes(self) -> bool:
        if not self._staged_db_entries or not self.repo:
            return True
        success = self.repo.save_batch_index_manifest(self._staged_db_entries)
        if success:
            self._staged_db_entries.clear()
        return success

    def sanitize_hierarchical_input(self, raw_parts) -> tuple[str, list] | None:
        """Sanitizes incoming arrays into safe tokens and slices."""
        if not raw_parts:
            return None
        if isinstance(raw_parts, (list, tuple)):
            if len(raw_parts) == 0:
                return None
            first = raw_parts[0]
            current_token = str(first[0]).strip() if isinstance(first, (list, tuple)) else str(first).strip()
            path_tail = list(raw_parts[1:])
        else:
            current_token = str(raw_parts).strip()
            path_tail = []
        return (current_token, path_tail) if current_token else None

    def evaluate_node_type(self, current_token: str) -> tuple[str, bool]:
        """Runs regex patterns to detect see/seealso keywords."""
        is_xref = False
        display_text = current_token
        if not current_token:
            return display_text, is_xref

        token_clean = current_token.strip()
        seealso_pattern = re.compile(r'^(?:\\|\|)?seealso:?\{?', re.IGNORECASE)
        see_pattern = re.compile(r'^(?:\\|\|)?see:?\{?', re.IGNORECASE)

        if seealso_pattern.search(token_clean):
            is_xref = True
            clean = seealso_pattern.sub("", token_clean).rstrip("}")
            display_text = f"See also {clean.strip()}"
        elif see_pattern.search(token_clean):
            is_xref = True
            clean = see_pattern.sub("", token_clean).rstrip("}")
            display_text = f"See {clean.strip()}"

        return display_text, is_xref

    def compile_transaction_record(self, clean_parts: list, ref_data: dict, encap: str, aid: int):
        """Compiles uncommitted metadata parameters for database staging."""
        h_path = " // ".join(clean_parts)
        macro = "!".join(clean_parts)
        v_tag = f"\\index{{{macro}|{encap}}}" if encap != "standard" else f"\\index{{{macro}}}"
        
        self._staged_db_entries.append({
            "id": int(aid), "entry_path": h_path,
            "file_path": os.path.normpath(str(ref_data.get("file_path", ""))),
            "line_number": int(ref_data.get("line_number", 0)), 
            "column_number": int(ref_data.get("column_offset", 0)),
            "encap_style": encap, "visual_tag": v_tag
        })
