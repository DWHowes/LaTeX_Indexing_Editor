import os
import re

from models import index_tag_grammar as grammar
from models.pending_changes_journal import DELETE, INSERT, PendingChangesJournal

class IndexTreeModelEngine:
    """
    Business Logic & Data Model.
    Tracks staged changes and parses raw LaTeX strings.
    Strict MVC: 100% decoupled from PySide6 widgets, fonts, and views.
    """
    def __init__(self, repository_model):
        self.repo = repository_model  # Database repository layer

        self._cross_reference_cache: dict = {}  

        self._active_headings: list = []
        # Heading ids are allocated here, not by SQLite -- see
        # resolve_heading_id. The journal holds heading rows created or
        # orphaned since the last save; both are written at save time,
        # same as references.
        self._next_heading_id: int = 1
        self._heading_journal = PendingChangesJournal("heading")
        self._active_references: list = []

    def clear_staged_entries(self) -> None:
        """Delegates to the full transaction reset for consistency."""
        self.reset_transaction_arrays()

    def reset_transaction_arrays(self) -> None:
        """
        Purges all volatile transactional caches from memory.
        Ensures a completely fresh tracking state for new project loads.
        """
        self._cross_reference_cache.clear()

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

    #: The label a cross-reference node is shown with. This much of the
    #: node -- and only this much -- is rendered in italic; see
    #: split_cross_reference.
    XREF_LABEL_SEE = "See"
    XREF_LABEL_SEEALSO = "See also"

    # Group 1 captures the opening brace when the token used the braced
    # form, so exactly that brace can be dropped again and braces
    # belonging to the target's own macros are left alone.
    _SEEALSO_PATTERN = re.compile(r'^(?:\\|\|)?seealso:?(\{)?', re.IGNORECASE)
    _SEE_PATTERN = re.compile(r'^(?:\\|\|)?see:?(\{)?', re.IGNORECASE)

    def split_cross_reference(self, current_token: str) -> tuple[str, str] | None:
        r"""
        Splits a see/seealso token into its ``(label, target)`` pair, or
        returns None when the token is not a cross-reference at all.

        The target comes back as *display* text: any sort key is resolved
        away level by level, so "Die Linke@\textit{Die Linke}" arrives as
        "\textit{Die Linke}". That has to happen here rather than being
        left to the delegate's '@' split, which runs on the whole cell
        string and would swallow the label along with the sort key.

        Formatting macros in the target are deliberately kept: they are
        what the target's own \index entry asks for, and the delegate
        renders them. Only the label is styled by this application.
        """
        if not current_token:
            return None

        token_clean = current_token.strip()
        # seealso must be tested first: the see pattern also matches the
        # leading "see" of "seealso".
        for pattern, label in (
            (self._SEEALSO_PATTERN, self.XREF_LABEL_SEEALSO),
            (self._SEE_PATTERN, self.XREF_LABEL_SEE),
        ):
            match = pattern.match(token_clean)
            if not match:
                continue
            raw_target = token_clean[match.end():].strip()
            if match.group(1) and raw_target.endswith("}"):
                raw_target = raw_target[:-1].strip()
            return label, self._cross_reference_target_display(raw_target)

        return None

    @staticmethod
    def _cross_reference_target_display(raw_target: str) -> str:
        """The target's display text, sort keys resolved on every level."""
        levels = grammar.split_levels_clean(raw_target)
        if not levels:
            return raw_target.strip()
        return grammar.join_levels(grammar.display_of(level) for level in levels)

    def evaluate_node_type(self, current_token: str) -> tuple[str, bool]:
        """Runs regex patterns to detect see/seealso keywords."""
        if not current_token:
            return current_token, False

        parsed = self.split_cross_reference(current_token)
        if parsed is None:
            return current_token, False

        label, target = parsed
        return f"{label} {target}".strip(), True

    def compile_and_retain_project_paths(self, file_paths: list[str]) -> tuple[list[dict], list[dict]]:
        """Invokes your scraper method, retains results in memory, and returns them."""
        self.reset_transaction_arrays()
        headings, references = self._scrape_and_compile_paths(file_paths)
        self._active_headings = headings
        self._active_references = references
        return headings, references
    
    def clear_active_manifests(self) -> None:
        """Purges all active workspace structures from cache tracking memory."""
        self._cross_reference_cache.clear()
        self._active_headings.clear()
        self._active_references.clear()
        self._heading_journal.clear()
        self._next_heading_id = 1

    def get_main_headings(self) -> list[tuple[str, str]]:
        """
        Returns (display_label, raw_token) pairs for every distinct main
        (top-level) heading currently loaded, deduped by raw_token and
        sorted case-insensitively by display_label. Feeds the Cross-
        References tab's Source/Cross-Ref dropdowns.

        Extracts the main-level segment (everything before the first "!")
        from EVERY loaded heading, regardless of that heading's own depth
        -- NOT just rows literally at depth == 0. A main heading that's
        purely an "umbrella" for sub-entries (e.g. every actual page
        reference is filed as "belief change!causal factors", "belief
        change!economic shock", etc., with no bare \\index{belief change}
        anywhere) never gets its own depth-0 project_headings row, only
        depth-1+ rows whose heading_text is the full compound path -- a
        depth-0-only filter would silently drop it from these dropdowns
        even though the index tree correctly shows it as a main node
        (the tree derives its parent nodes the same "!"-split way, not
        from a literal depth-0 row).

        raw_token is the exact token as it appears in \\index{...} (e.g.
        "Die Linke@\\textit{Die Linke} (Germany)") -- required for the
        Source side of a cross-reference, which must reuse the same raw
        token as the heading's other entries or makeindex will group it
        under a spurious duplicate heading. display_label is the post-"@"
        display portion (or the whole token when there's no "@" override),
        same split convention as entry_modifier_list._parse_index_level --
        reimplemented locally to keep this model layer free of a view-layer
        import.
        """
        seen: dict[str, str] = {}
        for heading in self._active_headings:
            raw_full = str(heading.get("heading_text") or "").strip()
            if not raw_full:
                continue
            raw = grammar.split_levels(raw_full)[0].strip()
            if not raw or raw in seen:
                continue
            display = grammar.display_of(raw)
            seen[raw] = display or raw

        return sorted(((display, raw) for raw, display in seen.items()), key=lambda pair: pair[0].lower())

    def ingest_pre_parsed_project_dataset(self, headings: list[dict], references: list[dict]) -> None:
        """
        Public Data Entry Contract.
        Ingests pre-extracted relational parameters directly into memory storage.
        """
        self.clear_active_manifests()
        self._active_headings = list(headings)
        self._active_references = list(references)
        self._reseed_heading_ids()

    # ------------------------------------------------------------------
    # Heading identity
    # ------------------------------------------------------------------

    def _reseed_heading_ids(self) -> None:
        """
        Re-seeds the in-memory heading id counter above every id currently
        loaded. Called after any full ingest, mirroring what
        AppPipelineController does with MacroIDGenerator for reference ids.
        """
        existing = [
            int(h.get("id")) for h in self._active_headings
            if h.get("id") is not None
        ]
        self._next_heading_id = (max(existing) + 1) if existing else 1

    @staticmethod
    def _heading_key(heading_text: str, depth: int) -> tuple[str, int]:
        """
        Identity of a heading row. Matches resolve_or_insert_heading's own
        SELECT, which keys on (heading_text, depth) -- not on text alone,
        so the two cannot disagree about what counts as the same heading.
        """
        return (str(heading_text), int(depth))

    def find_heading_id(self, heading_text: str) -> int | None:
        """Returns the id of an already-known heading, or None."""
        depth = grammar.depth_of(heading_text)
        key = self._heading_key(heading_text, depth)
        for heading in self._active_headings:
            if heading.get("id") is None:
                continue
            if self._heading_key(
                heading.get("heading_text") or heading.get("name") or "",
                heading.get("depth", 0),
            ) == key:
                return int(heading["id"])
        return None

    def resolve_heading_id(self, heading_text: str, parent_id: int | None = None) -> int | None:
        """
        Finds or creates the heading for heading_text and returns its id,
        **without touching the database**.

        Heading ids are allocated here rather than by SQLite's
        autoincrement so that a heading can be created while its row is
        still pending a write. ProjectLoadWorker already assigns them this
        way for a full load (and the bulk insert writes explicit ids), so
        this brings live insertion onto the same footing rather than
        introducing a new convention.

        Newly created headings are journalled for the save drain to
        write; nothing reaches the database here.
        """
        if not heading_text:
            return None

        existing = self.find_heading_id(heading_text)
        if existing is not None:
            return existing

        # Defensive rather than trusting the seed: _active_headings can be
        # populated by paths that never call ingest_pre_parsed_project_dataset
        # (a directly-built engine, a test fixture), which would leave the
        # counter at 1 and hand out an id that already belongs to a loaded
        # heading. Re-deriving the floor at allocation time makes a
        # collision impossible however the list was filled.
        highest_loaded = max(
            (int(h["id"]) for h in self._active_headings if h.get("id") is not None),
            default=0,
        )
        new_id = max(self._next_heading_id, highest_loaded + 1)
        self._next_heading_id = new_id + 1
        self._active_headings.append({
            "id": new_id,
            "parent_id": parent_id,
            "heading_text": heading_text,
            "name": heading_text,
            "depth": grammar.depth_of(heading_text),
        })
        self._heading_journal.mark_insert(new_id)
        return new_id

    def mark_heading_deleted(self, heading_id: int) -> None:
        """
        Records that a heading row should be removed at the next save.

        A heading created and orphaned within the same session cancels out
        in the journal, exactly as a reference does -- its row was never
        written, so neither the insert nor the delete should ever reach
        the database.
        """
        if heading_id is not None:
            self._heading_journal.mark_delete(int(heading_id))

    def resolve_heading_path(self, heading_text: str) -> int | None:
        """
        In-memory counterpart of FileTreePersistence.resolve_heading_path:
        resolves the heading together with its parent chain and returns its
        id. Depth and parent text come from index_tag_grammar, so an encap
        or a braced "!" never inflates the depth.
        """
        if not heading_text:
            return None

        parent_id = None
        if grammar.depth_of(heading_text) > 0:
            parent_text = grammar.parent_path(heading_text)
            if parent_text:
                parent_id = self.resolve_heading_id(parent_text)

        return self.resolve_heading_id(heading_text, parent_id)

    def has_pending_heading_changes(self) -> bool:
        return bool(self._heading_journal)

    def flush_heading_inserts(self, persistence) -> tuple[int, int]:
        r"""
        Writes every heading created in memory since the last save.

        Called BEFORE the reference flush: a reference row carries a
        heading_id, so the heading it names has to exist first.
        """
        if persistence is None:
            return 0, 0

        by_id = {h.get("id"): h for h in self._active_headings}
        succeeded = failed = 0
        for heading_id in self._heading_journal.entity_ids(INSERT):
            row = by_id.get(heading_id)
            if row is None:
                # Created and then pruned from _active_headings without the
                # deletion being marked -- nothing to write.
                self._heading_journal.resolve([heading_id])
                continue
            if persistence.insert_heading_with_id(row):
                succeeded += 1
            else:
                failed += 1
            self._heading_journal.resolve([heading_id])
        return succeeded, failed

    def flush_heading_deletes(self, persistence) -> tuple[int, int]:
        r"""
        Removes heading rows orphaned since the last save.

        Called AFTER the reference flush, for the mirror of the reason
        inserts go first: the references pointing at a heading have to be
        gone before the heading itself is.
        """
        if persistence is None:
            return 0, 0

        succeeded = failed = 0
        for heading_id in self._heading_journal.entity_ids(DELETE):
            if persistence.delete_heading_if_orphaned(heading_id):
                succeeded += 1
            else:
                failed += 1
            self._heading_journal.resolve([heading_id])
        return succeeded, failed
