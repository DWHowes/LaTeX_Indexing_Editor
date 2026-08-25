import os
from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QMessageBox

from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT as dialect
from models.latex_record_mapping import (
    command_of, end_of, position_of, row_from_reference,
)
from bookindexcore.model.records import IndexReference
from bookindexcore.model.commands import (
    EntrySnapshot,
    copy_record,
    HeadingChange,
    MacroEdit,
    deletion_command,
    edit_command,
)
from bookindexcore.backend.locator import Locator, SourceEdit
from bookindexcore.ui.tree.reference import TreeReference
from views.index_tree_view import IndexTreeView
from controllers.document_io_controller import DocumentIOController
from controllers.latex_text_backend import LatexTextBackend



def _ref_entry_id(ref) -> int:
    """
    The entry id of a reference payload stored on a tree node.

    Tolerant of three shapes on purpose. The entry *table* is fed records by
    the pipeline; the tree's ``UserRole+1`` ref-lists hold ``TreeReference``
    values since extraction step 9b; and a raw load payload still reaches
    some of these paths directly. **All four sites that used to inline this
    expression now call it**, which is what made adding the third shape one
    edit rather than four.
    """
    if isinstance(ref, (IndexReference, TreeReference)):
        return int(ref.entry_id or 0)
    return int(ref.get("unique_id_number") or ref.get("id") or 0)


class IndexEditController(QObject):
    r"""
    Owns the rewrite pipeline for existing \index macro edits.

    Responsibilities
    ----------------
    - Enable inline editing of index tree nodes (column 0, double-click)
    - On edit commit, rewrite all affected macro spans via DocumentIOController
    - Shift in-memory coordinates for all subsequent references in each
      affected file via EntryModifierModel
    - Clean up orphaned heading nodes after a rename

    This controller is intentionally separate from LatexIndexController,
    which owns only the *insertion* (create new macro) responsibility.
    """

    # Emitted after a successful rename so the app pipeline can mark the
    # project dirty and update any other interested parties.
    heading_renamed = Signal(str, str)   # old_raw_token, new_raw_token
    entry_deleted = Signal(int)          # entry_id of a deleted reference
    heading_rename_conflict = Signal(str, list)  # old_raw_token, blocking entry ids
    entry_reverted = Signal(int, str)    # entry_id, reverted canonical heading (discard rollback)
    # Emitted after any successful mutation, carrying the IndexCommand that
    # reverses it. AppPipelineController owns the stack and pushes these;
    # this controller stays unaware of undo depth or ordering. Nothing is
    # emitted from apply_command itself -- replaying a command must not
    # record a new one.
    command_recorded = Signal(object)    # IndexCommand

    def __init__(
        self,
        tree_view: IndexTreeView,
        doc_io: DocumentIOController,
        entry_modifier_model,   # EntryModifierModel — avoid circular import
        staging_model,          # IndexEditStagingModel — avoid circular import
        parent=None,
    ):
        super().__init__(parent)
        self._tree = tree_view
        self._doc_io = doc_io
        self._entry_model = entry_modifier_model
        self._staging_model = staging_model

        # This application's DocumentBackend, constructed here rather than
        # injected. Injecting it with a None default is what turned a stale
        # coordinate into a hung test suite once already: every construction
        # site that did not supply one silently stopped keeping positions in
        # step. It is cheap, it needs only the doc_io this controller already
        # holds, and AppPipelineController reads it back off here so that
        # there is exactly one entry table.
        self.text_backend = LatexTextBackend(doc_io)

        #: Containers already adopted inside a `bulk_writes` block, or None
        #: when not in one. See `bulk_writes` for why adopting once per
        #: command rather than once per write is correct as well as faster.
        self._bulk_adopted: set | None = None

        # Wire double-click to our handler — we disconnect the existing
        # navigation handler and re-route so we can split col 0 / col 1 behaviour.
        # The tree's existing doubleClicked connection (_process_embedded_metrics_click)
        # remains intact; we add our own connection and gate on column inside it.
        self._tree.doubleClicked.connect(self._on_tree_double_clicked)

        # When the base model signals that data changed (i.e. the inline editor
        # committed a value), intercept and drive the rewrite pipeline.
        self._tree.base_model.dataChanged.connect(self._on_tree_item_edited)

        # Guard flag — set True while we are programmatically updating the model
        # so _on_tree_item_edited doesn't re-enter.
        self._rewriting = False

    # ------------------------------------------------------------------
    # The write seam
    # ------------------------------------------------------------------

    @contextmanager
    def bulk_writes(self):
        r"""
        Adopt the backend's entry table **once** for a run of writes, instead
        of once per write.

        Correct rather than merely faster, and the reason is the backend's own
        design: :meth:`LatexTextBackend._shift_after` *maintains* the table as
        each edit lands, so a table adopted at the start of a command is still
        accurate at the end of it. Re-adopting per write was rebuilding, from
        the store, a table the backend had just finished updating itself.

        The saving is a whole factor of the cost. A command of *e* edits over
        an index of *n* entries was ``O(e x n)`` in adoption alone, on top of
        the ``O(e x n)`` the relocation sweep genuinely needs. Measured over a
        rename of every entry: 4,000 entries went from 109 seconds to a
        fraction of that. It is still quadratic in the worst case -- each edit
        really does move everything after it -- but the constant is what
        decides whether a tool is usable.

        Nested use is safe: an inner block joins the outer one rather than
        re-adopting, in the same way :meth:`IndexRepository.transaction` joins
        rather than nesting.
        """
        if self._bulk_adopted is not None:
            yield
            return
        self._bulk_adopted = set()
        try:
            yield
        finally:
            self._bulk_adopted = None

    def _adopt(self, container: str) -> None:
        """
        Bring the backend's table up to date with the store, unless a
        :meth:`bulk_writes` block has already done it for this container.
        """
        if self._bulk_adopted is not None:
            if container in self._bulk_adopted:
                return
            self._bulk_adopted.add(container)
        # Every record, not the ones this controller thinks are in the file:
        # adopt_entries normalises and filters, which puts the one place that
        # knows a container is a *path* in charge of deciding what counts as
        # the same file. Two spellings of one path would otherwise leave the
        # table short of entries, and a missing entry is one that never gets
        # told it moved.
        self.text_backend.adopt_entries(container, self._entry_model.all_records())

    def _write_span(self, entry_id: int, before: str, after: str) -> bool:
        r"""
        Rewrites one entry's source span through the backend, and brings the
        cache in step with whatever the backend says moved.

        **This is the whole of §4.2's arrangement, at one call site.** The
        backend performs the write, reports the entry's new position, and
        reports every other entry that moved as ``LocatorUpdate``s; the store
        applies those without asking what a position is. Passing ``""`` as
        ``after`` deletes, which is why deletion does not need its own method.

        The table is adopted immediately beforehand rather than scanned. The
        backend mints anchors from where macros are *now*; this application's
        anchors were minted at the scan that first filled its database and are
        identity rather than position. After any edit the two disagree, and
        the backend stops finding the entry it is being asked about --
        reporting, not unreasonably, that no such entry exists.

        Returns False without leaving a partial write behind. The backend
        refuses rather than guesses when the span no longer reads as
        ``before``, which is what stops a rewrite landing in the middle of a
        neighbouring word after somebody else has edited the file.
        """
        record = self._entry_model.get_record(entry_id)
        if record is None:
            print(f"[WRITE] no cached record for entry {entry_id}")
            return False

        self._adopt(record.locator.container)

        result = self.text_backend.apply(SourceEdit(
            entry_id=entry_id, locator=record.locator, before=before, after=after,
        ))
        if not result.ok:
            print(f"[WRITE] refused for entry {entry_id}: {result.message}")
            return False

        if result.locator is not None:
            # Merged, not assigned. A backend builds the hint it owns --
            # offsets and the macro name -- and knows nothing of the other
            # things this application keeps in there, so replacing wholesale
            # drops them. line_number and column_offset are NOT NULL columns,
            # so the symptom was a save that failed at the database rather
            # than anywhere near the edit that caused it.
            record.locator = record.locator.with_hint(**result.locator.hint)
            self._entry_model.mark_dirty(entry_id)

        for moved_id in self._entry_model.apply_relocations(result.relocations):
            self._entry_model.mark_dirty(moved_id)

        return True

    def place_macro(self, container: str, position: int, text: str):
        r"""
        Writes a new macro at ``position``, and brings the cache in step.

        The companion to :meth:`_write_span` for the one operation that names
        no existing entry. Its locator carries a place and no anchor, which is
        what ``apply`` reads as "put a new one here" — the shape the protocol
        gained in phase 5b, because the old ``insert(at)`` meant *beside an
        existing entry* and could not express a caret in a chapter that has no
        entries yet.

        Returns the backend's ``EditResult``. The caller needs the locator off
        it: the anchor the backend minted is the new entry's identity, and
        there is no other way to learn it.
        """
        self._adopt(container)

        result = self.text_backend.apply(SourceEdit(
            entry_id=None,
            locator=Locator(container, "", {"absolute_position": position}),
            before="",
            after=text,
        ))
        if not result.ok:
            print(f"[WRITE] placement refused in {os.path.basename(container)}: {result.message}")
            return result

        for moved_id in self._entry_model.apply_relocations(result.relocations):
            self._entry_model.mark_dirty(moved_id)
        return result

    def note_external_shift(self, container: str, position: int, delta: int) -> list:
        """
        Keeps positions in step after text this backend did not write.

        The generated-block injections — the preamble, custom commands, head
        notes, ``cross_refs.tex`` — splice straight into a file, so every entry
        after the splice point moves with no ``SourceEdit`` involved. The
        backend has an entry point for exactly that, and skipping it leaves
        entries whose coordinates are stale, which the next write guard
        refuses rather than corrects.
        """
        self._adopt(container)
        moved = self._entry_model.apply_relocations(
            self.text_backend.shift_after(container, position, delta)
        )
        for moved_id in moved:
            self._entry_model.mark_dirty(moved_id)
        return moved

    # ------------------------------------------------------------------
    # Inline edit activation
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_tree_double_clicked(self, index):
        """
        Routes double-clicks by column.

        Column 0 — activate inline edit for the heading token at this depth.
        Column 1 — leave navigation to the existing _process_embedded_metrics_click
                   handler already connected in IndexTreeView.__init__.
        """
        if not index.isValid() or index.column() != 0:
            return

        # Temporarily enable editing for this single item only, then
        # restore NoEditTriggers immediately after the editor opens so
        # the user cannot accidentally trigger edits on other items.
        item = self._tree.base_model.itemFromIndex(index)
        if item is None:
            return

        # Store the original raw token so we can compute the delta on commit
        raw_token = item.data(Qt.ItemDataRole.ToolTipRole) or item.text()
        item.setData(raw_token, Qt.ItemDataRole.UserRole + 10)   # stash pre-edit value

        # edit(QModelIndex) opens the editor unconditionally — it does not
        # consult editTriggers() at all (that overload only matters for
        # Qt's own internal open-on-trigger checks). Toggling triggers on
        # and back off around this call therefore does nothing useful,
        # and it's actively harmful: this slot runs from inside
        # doubleClicked, which itself fires from inside
        # QAbstractItemView::mouseDoubleClickEvent(). That method rechecks
        # the current trigger state immediately after the signal emission
        # returns, to decide whether it should also open an editor itself.
        # Flipping editTriggers on then back off while still on that same
        # call stack is what was corrupting the view's persistent-editor
        # bookkeeping, producing "editor does not belong to this view"
        # once the editor was later closed. editTriggers stays permanently
        # NoEditTriggers (set in IndexTreeView.__init__) so no other path
        # (F2, single click, etc.) can open an editor — only this explicit
        # call does.
        self._tree.edit(index)

    # ------------------------------------------------------------------
    # Edit commit handler
    # ------------------------------------------------------------------

    @Slot(object, object, list)
    def _on_tree_item_edited(self, top_left, bottom_right, roles):
        """
        Fires when the inline editor commits a value to the base model.

        IMPORTANT: this fires synchronously from inside the view's own
        commitData() -> closeEditor() sequence — the delegate writes the
        edited text into the model, which raises dataChanged right there,
        before the view has finished tearing down its persistent editor
        for this index. The actual rewrite pipeline below does heavy
        model/tree mutation (restoring item text on a failed rewrite,
        and heading_renamed potentially driving a tree repopulation
        elsewhere in the pipeline) — doing that here, still mid-call-stack
        inside commitData/closeEditor, can replace or destroy the model
        out from under the view before it finishes, which is exactly what
        produces Qt's "editor does not belong to this view" warnings and
        silently aborts the pipeline before it reaches the table or the
        .tex file.

        So only cheap, read-only validity checks happen here. The real
        work is scheduled for the next event-loop tick via
        QTimer.singleShot(0, ...), by which point the view has fully
        finished closing its editor and this handler is no longer on that
        call stack.
        """

        if self._rewriting:
            return
        if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
            return
        if top_left.column() != 0:
            return

        item = self._tree.base_model.itemFromIndex(top_left)
        if item is None:
            return

        new_display = item.text().strip()
        old_raw_token = item.data(Qt.ItemDataRole.UserRole + 10)

        if not new_display or new_display == old_raw_token:
            return  # nothing changed or empty — nothing to do
        if not old_raw_token:
            return

        QTimer.singleShot(
            0, lambda: self._process_heading_rename(item, old_raw_token, new_display)
        )

    def _process_heading_rename(self, item: QStandardItem, old_raw_token: str, new_raw_token: str) -> None:
        """
        The actual rewrite pipeline, deferred out of the commitData/
        closeEditor call stack by _on_tree_item_edited. See that method's
        docstring for why this split exists.
        """
        # The item (or its model) may have gone away between scheduling
        # and this tick firing — e.g. a project close in the interim.
        # item is a wrapped C++ QStandardItem: if the model was torn down
        # in that window, touching it at all (not just item.model())
        # raises RuntimeError rather than returning None, so this is
        # caught explicitly rather than relying on a None check alone.
        try:
            if item is None or item.model() is None:
                return
        except RuntimeError:
            return

        # Captured before ToolTipRole is updated below (item's ToolTipRole
        # still holds the pre-rename token at this point) -- needed to patch
        # _active_headings afterward. See _update_active_headings_prefix's
        # docstring for why that patch is necessary.
        old_path_parts = self._collect_node_path(item)

        # Collect all references under this node (column 1 sibling, UserRole+1)
        affected_refs = self._collect_refs_from_node(item)
        if not affected_refs:
            self._restore_item_text(item, old_raw_token)
            return

        # ------------------------------------------------------------
        # Stage 5: conflict guard
        # ------------------------------------------------------------
        # A heading rename rewrites every reference sharing this node in
        # one atomic sweep. If any of those references already has an
        # unsaved, in-flight edit staged from the table side (user is
        # mid-edit on that row, not yet finalized via
        # EntryModifierController._finalize_row_edit), proceeding here
        # would silently clobber it: the rewrite loop below calls
        # stage_edit() with a value computed from the stale cached
        # heading, discarding whatever the table had staged, and its
        # .tex write targets coordinates the table's own finalize is
        # also about to write to. The whole rename is blocked rather
        # than applied to only the unaffected entries — a rename that
        # lands on some but not all of a node's children would leave
        # the tree node itself out of sync with its own subtree.
        conflict_ids = sorted({
            uid for uid in (
                _ref_entry_id(ref) for ref in affected_refs
            )
            if uid and self._staging_model.is_dirty(uid)
        })
        if conflict_ids:
            self._restore_item_text(item, old_raw_token)
            self.heading_rename_conflict.emit(old_raw_token, conflict_ids)
            QMessageBox.warning(
                self._tree,
                "Rename blocked",
                "This heading can't be renamed right now because "
                f"{len(conflict_ids)} of its entries have an edit in "
                "progress in the entry table. Finish that edit (move to "
                "another row, or press Enter) and try the rename again."
            )
            return

        # Build the old and new macro text for each reference and rewrite
        success_count = 0
        recorder: list = []
        self._rewriting = True
        try:
            for ref in affected_refs:
                result = self._rewrite_single_reference(
                    ref, old_raw_token, new_raw_token, recorder
                )
                if result:
                    success_count += 1
        finally:
            self._rewriting = False

        if success_count == 0:
            self._restore_item_text(item, old_raw_token)
            return

        # One command for the whole sweep: renaming a heading is a single
        # user action even though it rewrites every reference beneath it,
        # possibly across several files.
        if recorder:
            self.command_recorded.emit(edit_command(
                f"Rename heading to {new_raw_token}",
                [edit for edit, _change in recorder],
                [change for _edit, change in recorder],
            ))

        # Update the node's ToolTipRole to the new raw token
        item.setData(new_raw_token, Qt.ItemDataRole.ToolTipRole)
        item.setData(None, Qt.ItemDataRole.UserRole + 10)   # clear stash

        # Update sort key on the CaseInsensitiveItem
        if hasattr(item, 'sort_key'):
            item.sort_key = item._compute_clean_sort_key(new_raw_token)

        new_path_parts = old_path_parts[:-1] + [new_raw_token] if old_path_parts else [new_raw_token]
        self._update_active_headings_prefix(self._tree.engine, old_path_parts, new_path_parts)

        self.heading_renamed.emit(old_raw_token, new_raw_token)

    def _update_active_headings_prefix(
        self, engine, old_path_parts: list[str], new_path_parts: list[str]
    ) -> None:
        r"""
        Rewrites heading_text/name in engine._active_headings for the
        renamed node itself and every descendant heading, replacing the
        old path prefix (root..renamed node) with the new one.

        _process_heading_rename only ever changes the tree QStandardItem's
        own text/ToolTipRole and each reference's cached heading_raw_text
        -- unlike the table-edit path (_reconcile_heading_node), it never
        touched _active_headings, so a heading's registry entry (the
        source _find_heading_id_by_text/_create_heading_in_engine consult
        for every id lookup, including the orphan check that runs when a
        tab is discarded) permanently disagreed with the tree's actual
        displayed text after any tree-side rename. That gap is what let a
        discard-triggered detach from the renamed node's heading always
        fail to find its heading_id (no _active_headings entry existed
        under the new text), so the now-empty node was never recognized as
        orphaned and never pruned -- it just sat there as a dead node with
        no children.
        """
        if not old_path_parts:
            return
        old_prefix_norm = [p.strip().lower() for p in old_path_parts]
        depth = len(old_prefix_norm)

        for head in engine._active_headings:
            heading_text = head.get("heading_text") or head.get("name") or ""
            parts = dialect.split_levels_clean(heading_text)
            if len(parts) < depth:
                continue
            if [p.lower() for p in parts[:depth]] != old_prefix_norm:
                continue
            new_parts = list(new_path_parts) + parts[depth:]
            new_heading_text = dialect.join_levels(new_parts)
            head["heading_text"] = new_heading_text
            head["name"] = new_heading_text

    # ------------------------------------------------------------------
    # Reference collection
    # ------------------------------------------------------------------

    def _collect_refs_from_node(self, item: QStandardItem) -> list[dict]:
        """
        Collects all reference dicts stored under this node and its
        descendants (UserRole+1 on column 1 siblings).
        """
        refs = []
        self._collect_refs_recursive(item, refs)
        return refs

    def _collect_refs_recursive(self, item: QStandardItem, out: list) -> None:
        row_idx = item.row()
        parent = item.parent() or self._tree.base_model.invisibleRootItem()
        sibling_col1 = parent.child(row_idx, 1)
        if sibling_col1:
            stored = sibling_col1.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(stored, list):
                out.extend(stored)
            elif isinstance(stored, dict):
                out.append(stored)

        for child_row in range(item.rowCount()):
            child = item.child(child_row, 0)
            if child:
                self._collect_refs_recursive(child, out)

    # ------------------------------------------------------------------
    # Per-reference rewrite
    # ------------------------------------------------------------------

    def _rewrite_single_reference(
        self,
        ref: dict,
        old_raw_token: str,
        new_raw_token: str,
        recorder: list | None = None,
    ) -> bool:
        """
        Rewrites one reference's macro for a heading rename.

        ``recorder``, when given, collects this rewrite's (MacroEdit,
        HeadingChange) pair. A rename sweeps every reference under a node
        and is one user action, so _process_heading_rename accumulates the
        whole sweep and records a single command for it rather than one
        per reference.
        """
        uid = _ref_entry_id(ref)
        if uid == 0:
            return False

        location = self._entry_model.get_location_metadata(uid)
        if location is None:
            return False

        file_path = location.get("file_path", "")
        abs_pos = location.get("absolute_position")
        abs_end = location.get("absolute_end")

        if not file_path or abs_pos is None or abs_end is None:
            return False

        current_heading = self._entry_model.get_heading_text(uid)
        if not current_heading:
            return False

        new_heading = self._substitute_token_in_heading(
            current_heading, old_raw_token, new_raw_token
        )
        if new_heading == current_heading:
            return False

        record = self._entry_model.get_record(uid)
        command_name = command_of(record) if record else "index"

        # Record the intended value before attempting the .tex write, so the
        # staging model reflects "what the controller currently believes
        # this entry's heading is" even while the write is in flight.
        self._staging_model.stage_edit(uid, new_heading)

        old_macro = self._doc_io.read_macro_span(file_path, abs_pos, abs_end) or ""

        # heading_raw_text never carries the "|encap" suffix on any load
        # path -- the parser splits it off before storing -- so rebuilding
        # the macro from it alone silently DELETED that suffix from the
        # .tex file: renaming a heading turned "\index{Main|textbf}" into
        # "\index{Renamed}", and "\index{Main|(}" into "\index{Renamed}",
        # destroying the range along with it. The suffix is read back off
        # the macro actually on disk (the same source _sync_range_partner
        # trusts, and for the same reason) and re-attached here.
        #
        # Only the written macro carries it. record["heading_raw_text"]
        # below deliberately stays encap-free, since heading resolution
        # and tree reconciliation both key on the bare heading chain.
        new_macro_body = self._reattach_encap(old_macro, new_heading, command_name)

        # The index class is outside the braces and so is not in
        # heading_raw_text either. Same argument as the encap above, same
        # consequence if it is dropped: a rename would move the entry out of
        # its named index and into the default one.
        new_macro = grammar.build_macro(
            new_macro_body, command=command_name,
            index_class=grammar.index_class_of(old_macro, grammar.command_pattern(command_name)),
        )
        if not self._write_span(uid, old_macro, new_macro):
            # Write did not happen — revert the staged value so it doesn't
            # drift out of sync with what's actually on the .tex source.
            self._staging_model.discard(uid)
            return False

        if record:
            record.heading_raw = new_heading

        if recorder is not None and old_macro:
            recorder.append((
                MacroEdit(uid, file_path, abs_pos, old_macro, new_macro, command_name),
                HeadingChange(uid, current_heading, new_heading),
            ))

        # .tex write confirmed successful — promote staged to original.
        self._staging_model.commit(uid)

        # Keep this entry's range partner (if any) in sync -- see
        # _sync_range_partner's docstring for why this wasn't happening at
        # all beforehand. The full body goes over, encap included: the
        # partner takes its heading chain and its page style from here,
        # and keeps only its own range marker.
        self._sync_range_partner(uid, new_macro_body)

        return True

    # ------------------------------------------------------------------
    # Heading token substitution
    # ------------------------------------------------------------------

    @staticmethod
    def _substitute_token_in_heading(
        heading_raw_text: str,
        old_token: str,
        new_token: str,
    ) -> str:
        """
        Substitutes old_token with new_token at the matching level in
        heading_raw_text, respecting brace depth for the ! level splitter.

        Only substitutes the first exact match (case-insensitive on the
        sort-key portion) so that editing a sub-level doesn't accidentally
        replace a same-named main level.

        Parsing is strip=False throughout: this rewrites heading text that
        goes straight back into a macro span, so surrounding whitespace is
        the caller's to keep, not this method's to normalize away.
        """
        tag = grammar.parse_body(heading_raw_text, strip=False)

        substituted = False
        new_levels = []
        old_sort = dialect.sort_key_of(old_token).lower()

        for level in tag.levels:
            if not substituted and dialect.sort_key_of(level).lower() == old_sort:
                new_levels.append(new_token)
                substituted = True
            else:
                new_levels.append(level)

        return tag.with_levels(new_levels).to_body()

    @staticmethod
    def _strip_encap_suffix(heading_text: str) -> str:
        """
        Returns heading_text with any trailing "|encap" suffix removed,
        respecting brace depth. No-ops if there's no unbraced "|".
        """
        return grammar.strip_encap(heading_text, strip=False)

    @staticmethod
    def _reattach_encap(old_macro: str, new_heading: str, command_name: str) -> str:
        r"""
        Puts back the "|encap" suffix that ``old_macro`` carried on disk,
        for a ``new_heading`` rebuilt from encap-free cached text.

        A heading that already carries a suffix keeps its own -- that is
        the table-edit path, where the user's Page-column choice is
        authoritative and the on-disk value is precisely what is being
        replaced. Only the rename path, whose input is heading_raw_text,
        arrives here with nothing to keep.

        An unreadable or unparseable ``old_macro`` yields the heading
        unchanged rather than a guess: losing a suffix that could not be
        read is no worse than the behaviour being fixed, whereas
        inventing one would corrupt a macro that was fine.
        """
        if grammar.split_encap(new_heading, strip=False)[1]:
            return new_heading

        tag = grammar.parse_macro(old_macro, grammar.build_macro_pattern([command_name]))
        if tag is None or not tag.encap:
            return new_heading

        return f"{new_heading}{grammar.ENCAP_SEPARATOR}{tag.encap}"

    # ------------------------------------------------------------------
    # Range-partner syncing
    # ------------------------------------------------------------------

    def _sync_range_partner(self, entry_id: int, new_heading: str) -> bool:
        r"""
        If entry_id is one half of a \index range pair (range_partner_id
        set on its cached record), rewrites the partner's macro so both
        halves keep an identical heading chain — makeindex requires the
        opener and closer to share the exact same path for the range to
        be recognised as one range rather than two unrelated entries.

        range_partner_id is assigned at insert time (see
        LatexIndexController.insert_latex and
        AppPipelineController._handle_manual_index_insertion) but nothing
        in this controller ever consulted it before this method existed —
        confirmed by there being no other reference to range_partner_id
        anywhere in this file. That gap is what let a table edit rewrite
        only the one entry_id it was given (leaving the other half of the
        range with its original, now-mismatched heading indefinitely),
        while a tree rename would only reach whatever refs happened to
        already be attached to the renamed node — and
        IndexTreeView.populate_hierarchy_tree explicitly excludes range
        closers from every node's ref list. This method is the one place
        that now closes that gap for both call sites.

        ``new_heading`` is the primary entry's full new tag body, encap
        included — the partner needs both halves of it, for two different
        reasons.

        The partner's own "(" / ")" marker — necessarily the opposite one
        from entry_id's — is preserved exactly as it currently stands on
        disk: neither heading_raw_text (which never includes encap,
        across every loading path in this codebase) nor the cached
        "encap" field (whose meaning differs between the regex-fallback
        scan and the live-insert path — see read_macro_span's docstring)
        can be trusted as the source of truth for it, so it's read
        directly via DocumentIOController.read_macro_span instead.

        The partner's *page style*, on the other hand, is copied from the
        primary rather than preserved, so that both ends of a range name
        the same command ("|(textbf" ... "|)textbf"). Verified against
        makeindex 2.17: the opening encapsulator is the one that wins,
        and a closer carrying a *different* non-empty one draws "Range
        closing operator has an inconsistent encapsulator" in the .ilg.
        The range still forms either way — this is a warning, not an
        error — but a file whose two halves disagree is a file whose
        style silently depends on which half the user last touched.

        Since the entry table only ever shows the opener (closers are
        coordinate-only records, excluded from the table and the tree),
        styling the opener is the only way a user can style a range at
        all — so it has to carry to the half they cannot see. Only the
        command half moves; if either side turns out not to be a range
        encap after all, the partner's suffix is left alone.

        No-ops (returns True) if entry_id has no range partner. Returns
        False if a partner exists but syncing it failed — callers should
        treat that as a partial-success condition to warn about rather
        than a reason to fail the whole edit, since by the time this
        runs the primary entry's own rewrite has already succeeded.
        """
        record = self._entry_model.get_record(entry_id)
        partner_id = record.range_partner_id if record else None
        if not partner_id:
            return True

        partner_location = self._entry_model.get_location_metadata(partner_id)
        if partner_location is None:
            print(f"[CONTROLLER WARNING] _sync_range_partner: no location for partner {partner_id}")
            return False

        partner_file = partner_location.get("file_path", "")
        partner_pos = partner_location.get("absolute_position")
        partner_end = partner_location.get("absolute_end")
        if not partner_file or partner_pos is None or partner_end is None:
            print(f"[CONTROLLER WARNING] _sync_range_partner: incomplete coordinates for partner {partner_id}")
            return False

        partner_record = self._entry_model.get_record(partner_id)
        partner_command = command_of(partner_record) if partner_record else "index"

        current_partner_macro = self._doc_io.read_macro_span(partner_file, partner_pos, partner_end)
        # Where the body starts depends on whether the macro carries an
        # index class, so it is asked for rather than assumed: the fixed
        # prefix this used to slice by is one character short of the truth
        # for every entry in a named index.
        body_start = grammar.macro_body_start(current_partner_macro or "", partner_command)
        if (
            current_partner_macro is None
            or body_start == -1
            or not current_partner_macro.endswith("}")
        ):
            print(
                f"[CONTROLLER WARNING] _sync_range_partner: unexpected span "
                f"content for partner {partner_id}: {current_partner_macro!r}"
            )
            return False

        new_heading_no_encap = self._strip_encap_suffix(new_heading)
        new_encap = grammar.split_encap(new_heading, strip=False)[1]

        partner_inner = current_partner_macro[body_start + 1:-1]
        partner_heading_only = self._strip_encap_suffix(partner_inner)
        partner_encap = (
            partner_inner[len(partner_heading_only) + 1:]
            if len(partner_inner) > len(partner_heading_only)
            else ""
        )

        # Carry the primary's page style over to the partner, keeping the
        # partner's own marker -- see this method's docstring for why the
        # two halves are treated differently.
        partner_role = dialect.range_role(partner_encap)
        primary_role, primary_command = grammar.split_range_encap(new_encap)
        if partner_role and primary_role:
            partner_encap = grammar.build_range_encap(partner_role, primary_command)

        new_partner_heading = (
            f"{new_heading_no_encap}|{partner_encap}" if partner_encap else new_heading_no_encap
        )
        if new_partner_heading == partner_inner:
            return True  # already in sync — nothing to do

        new_partner_macro = grammar.build_macro(
            new_partner_heading, command=partner_command,
            index_class=grammar.index_class_of(
                current_partner_macro, grammar.command_pattern(partner_command)
            ),
        )
        if not self._write_span(partner_id, current_partner_macro, new_partner_macro):
            print(f"[CONTROLLER WARNING] _sync_range_partner: rewrite rejected for partner {partner_id}")
            return False

        if partner_record:
            partner_record.heading_raw = new_heading_no_encap

        return True

    # ------------------------------------------------------------------
    # Shared service API — called by EntryModifierController
    # ------------------------------------------------------------------

    def handle_entry_table_edit(
        self,
        entry_id: int,
        new_canonical_heading: str,
    ) -> bool:
        location = self._entry_model.get_location_metadata(entry_id)
        if location is None:
            return False

        file_path = location.get("file_path", "")
        abs_pos = location.get("absolute_position")
        abs_end = location.get("absolute_end")

        if not file_path or abs_pos is None or abs_end is None:
            return False

        old_heading = self._entry_model.get_heading_text(entry_id)
        if not old_heading:
            return False

        if new_canonical_heading == old_heading:
            return True

        record = self._entry_model.get_record(entry_id)
        command_name = command_of(record) if record else "index"

        old_macro = self._doc_io.read_macro_span(file_path, abs_pos, abs_end) or ""

        new_macro = grammar.build_macro(
            new_canonical_heading, command=command_name,
            index_class=grammar.index_class_of(old_macro, grammar.command_pattern(command_name)),
        )
        if not self._write_span(entry_id, old_macro, new_macro):
            return False

        if old_macro:
            self.command_recorded.emit(edit_command(
                "Edit index entry",
                [MacroEdit(entry_id, file_path, abs_pos, old_macro, new_macro, command_name)],
                [HeadingChange(entry_id, old_heading, new_canonical_heading)],
            ))

        if record:
            record.heading_raw = new_canonical_heading

        # Keep this entry's range partner (if any) in sync -- this is the
        # actual fix for table edits only ever updating the range opener
        # and leaving the closer with its original heading text. Nothing
        # in this controller ever consulted range_partner_id before this.
        # The encap travels too -- the Page column is the one place a
        # range's style can be set, and the closer is never shown there.
        self._sync_range_partner(entry_id, new_canonical_heading)

        self._reconcile_heading_node(entry_id, old_heading, new_canonical_heading)

        return True

    def handle_entry_deletion(self, entry_id: int) -> bool:
        r"""
        Shared service API — permanently deletes a single \index reference.

        Mirrors handle_entry_table_edit's shape (same location-metadata
        guard, same rewrite_macro_span + coordinate-shift sequence) but
        rewrites the macro span to an empty string instead of a new
        heading, then removes rather than updates the model cache and
        reconciles the tree by removing this reference's entry from the
        heading node's display, pruning the node entirely if no
        references remain under its heading_id.

        This is the single entry point for reference deletion regardless
        of origin — EntryModifierController._perform_row_deletion (table)
        and any future tree-side "delete reference" context-menu action
        both call this directly, so the .tex write, coordinate shift, and
        cache/tree cleanup only exist in one place. entry_deleted is
        emitted on success so any view that didn't initiate the deletion
        (i.e. the table, when a tree-originated delete lands here) can
        remove its own row without a full reload.
        """
        location = self._entry_model.get_location_metadata(entry_id)
        if location is None:
            return False

        file_path = location.get("file_path", "")
        abs_pos = location.get("absolute_position")
        abs_end = location.get("absolute_end")
        heading_id = location.get("heading_id")

        if not file_path or abs_pos is None or abs_end is None:
            return False

        heading_text = self._entry_model.get_heading_text(entry_id)

        record = self._entry_model.get_record(entry_id)
        command_name = command_of(record) if record else "index"

        # Snapshot before the write: the record, its heading and its tree
        # path are all about to be torn down, and undo has to put every
        # one of them back.
        snapshot = self._snapshot_entry(entry_id)
        old_macro = self._doc_io.read_macro_span(file_path, abs_pos, abs_end) or ""

        # An empty `after` is a deletion -- SourceEdit says so, and expressing
        # it as an edit rather than a separate kind is what lets a command
        # holding a mixture invert by inverting each of its edits.
        if not self._write_span(entry_id, old_macro, ""):
            return False

        self._cleanup_deleted_entry(entry_id, heading_text, heading_id)

        if snapshot is not None and old_macro:
            self.command_recorded.emit(deletion_command(
                "Delete index entry",
                [MacroEdit(entry_id, file_path, abs_pos, old_macro, "", command_name)],
                [snapshot],
            ))
        return True

    def _snapshot_entry(self, entry_id: int):
        """
        Captures everything undo needs to recreate one reference: its full
        record, the tree path it sits under, and its heading identity.
        Returns None if the entry isn't in the cache.
        """
        record = self._entry_model.get_record(entry_id)
        if record is None:
            return None

        heading_text = record.heading_raw
        return EntrySnapshot(
            entry_id=entry_id,
            record=record,
            parts_list=tuple(dialect.level_path(heading_text)),
            heading_text=heading_text,
            heading_id=record.heading_id,
            is_range_closer=record.is_range_closer,
        )

    def count_refs_under_node(self, target_item: QStandardItem) -> int:
        """
        Public read-only helper for the delete-term confirmation dialog:
        how many distinct \\index references (openers + their range
        partners) would handle_node_deletion actually remove.
        """
        return len(self._distinct_entry_ids_under_node(target_item))

    def _distinct_entry_ids_under_node(self, target_item: QStandardItem) -> list[int]:
        """
        Collects every reference under target_item and its descendants
        (via _collect_refs_from_node, which only ever holds openers — see
        its docstring), plus each opener's range partner (closer), which
        is never in the tree's own ref lists and would otherwise be left
        behind as an orphaned "|)"-only macro with no matching opener.
        """
        entry_ids: list[int] = []
        seen: set[int] = set()
        for ref in self._collect_refs_from_node(target_item):
            uid = _ref_entry_id(ref)
            if not uid or uid in seen:
                continue
            seen.add(uid)
            entry_ids.append(uid)

            record = self._entry_model.get_record(uid)
            partner_id = record.range_partner_id if record else None
            if partner_id and partner_id not in seen:
                seen.add(partner_id)
                entry_ids.append(partner_id)

        return entry_ids

    def handle_node_deletion(self, target_item: QStandardItem) -> tuple[int, int]:
        r"""
        Permanently deletes an entire heading node and everything under
        it: every \index reference at or below this node (including range
        partners), their DB rows, and every heading row (this node's own
        and any descendant's) that ends up with zero references.

        Bulk counterpart to handle_entry_deletion, reusing it per-entry so
        the .tex rewrite / coordinate-shift / cache-and-view cleanup
        pipeline for a single reference only exists in one place. Entries
        can be processed in any order — shift_coordinates_after keeps
        every other cached record's coordinates correct after each
        individual deletion, so there's no ordering dependency between
        them even when several live in the same file.

        Returns (success_count, failure_count) across every reference
        processed (openers and their range partners).
        """
        path = self._collect_node_path(target_item)  # capture before any mutation
        entry_ids = self._distinct_entry_ids_under_node(target_item)

        success_count = 0
        failure_count = 0
        for entry_id in entry_ids:
            if self.handle_entry_deletion(entry_id):
                success_count += 1
            else:
                failure_count += 1

        self._prune_subtree_and_ancestors(path)

        return success_count, failure_count

    def _collect_node_path(self, item: QStandardItem) -> list[str]:
        """Collects raw ToolTipRole tokens from the root down to item."""
        tokens: list[str] = []
        node = item
        while node is not None:
            tokens.insert(0, str(node.data(Qt.ItemDataRole.ToolTipRole) or node.text()).strip())
            node = node.parent()
        return tokens

    def _prune_subtree_and_ancestors(self, parts: list[str]) -> None:
        r"""
        After a bulk deletion, cleans up two kinds of leftover empty nodes
        that handle_entry_deletion's own single-level, single-node orphan
        check can't reach on its own:

        1. Zombie nodes WITHIN the target's own former subtree. That
           per-entry orphan check only ever inspects the one node it just
           made referenceless — it refuses to remove it while it still has
           tree children (correctly, to avoid deleting a live subtree
           along with it via QStandardItemModel's cascading removeRow),
           but never comes back to recheck it later. In a bulk delete,
           processing a node's OWN direct entry before one of its
           children's entries (a real, common ordering from
           _collect_refs_from_node's traversal) leaves exactly that node
           behind: heading-orphaned in the DB already, but still sitting
           in the tree as a childless-looking parent until this sweep.
        2. Now-empty ancestors ABOVE the target's own level — e.g. an
           intermediate heading with no \index macro of its own, only
           existing as a parent row because resolve_or_insert_heading
           creates one for every ancestor level of a fresh insertion, so
           it was never the heading_id any single deleted entry pointed
           to and _remove_orphaned_heading never ran for it.

        Re-queries the tree by path throughout (rather than holding onto
        target_item, which may already be a dangling/removed
        QStandardItem by the time this runs) for both.
        """
        node = self._find_tree_node_by_path(parts)
        if node is not None:
            self._prune_node_subtree_bottom_up(node)

        engine = self._tree.engine
        for depth in range(len(parts), 0, -1):
            sub_parts = parts[:depth]
            ancestor = self._find_tree_node_by_path(sub_parts)
            if ancestor is None:
                continue  # already pruned above, or as a side effect of an entry delete

            # An ancestor can carry its own direct \index reference AND
            # have children at the same time (e.g. both \index{Sports} and
            # \index{Sports!Football} legitimately exist) -- unlike nodes
            # WITHIN the just-deleted subtree (which are guaranteed to have
            # had every one of their own references deleted already, see
            # this method's docstring), an ancestor's own ref list was
            # never touched by that deletion. Checking only rowCount()
            # here would prune a still-referenced ancestor the moment its
            # last CHILD is removed, silently vanishing it from the tree
            # and _active_headings even though its own \index macro is
            # still on disk and still tracked in the DB.
            if ancestor.rowCount() > 0 or self._node_has_own_refs(ancestor):
                break  # still has live children or its own reference — nothing shallower needs pruning either

            self._prune_single_node(sub_parts, engine)

    def _node_has_own_refs(self, node: QStandardItem) -> bool:
        """Whether node's own column-1 sibling still carries any reference."""
        parent = node.parent() or self._tree.base_model.invisibleRootItem()
        sibling_col1 = parent.child(node.row(), 1)
        if sibling_col1 is None:
            return False
        return bool(sibling_col1.data(Qt.ItemDataRole.UserRole + 1))

    def _prune_node_subtree_bottom_up(self, node: QStandardItem) -> None:
        r"""
        Recursively removes childless, heading-orphaned descendants of
        node, post-order (children before parents) — so a node that only
        became truly empty because ITS OWN child was pruned earlier in
        this same sweep gets caught too. Safe to run unconditionally
        across node's whole subtree: by the time handle_node_deletion
        calls this, every \index reference anywhere under node has
        already been deleted, so nothing legitimate should be left.
        """
        # Snapshot children before recursing — rows shift as siblings are removed.
        children = [node.child(r, 0) for r in range(node.rowCount())]
        for child in children:
            if child is not None:
                self._prune_node_subtree_bottom_up(child)

        if node.rowCount() > 0:
            return  # still has live children after the recursive pass below it

        parts = self._collect_node_path(node)
        self._prune_single_node(parts, self._tree.engine)

    def _prune_single_node(self, parts: list[str], engine) -> None:
        """Removes exactly one tree node by path plus its heading row, if any."""
        heading_id = self._find_heading_id_by_text(engine, dialect.join_levels(parts))
        self._remove_tree_node_by_path(parts)

        if heading_id is not None:
            engine._active_headings = [
                h for h in engine._active_headings if h.get("id") != heading_id
            ]
            engine.mark_heading_deleted(heading_id)

    def discard_uncommitted_entry(self, entry_id: int) -> bool:
        r"""
        Rolls back a single \index entry that was inserted earlier in this
        session but never saved — used when the user closes a tab (or the
        whole app) and chooses Discard.

        Unlike handle_entry_deletion, this does NOT call rewrite_macro_span:
        the caller is already restoring the file's entire buffer/on-disk
        content from its pristine session backup (see
        WorkspaceLifecycleController.discard_unsaved_changes /
        SessionBackupManager.restore_file_from_backup), so surgically
        editing the macro span here would be redundant and would race that
        wholesale restore. Only the DB row, in-memory cache, staging
        baseline, and tree/table views need cleanup — the same cleanup
        handle_entry_deletion performs after its own .tex rewrite.
        """
        location = self._entry_model.get_location_metadata(entry_id)
        if location is None:
            return False

        heading_id = location.get("heading_id")
        heading_text = self._entry_model.get_heading_text(entry_id)

        self._cleanup_deleted_entry(entry_id, heading_text, heading_id)
        return True

    def discard_dirty_edits(self, file_path: str) -> None:
        r"""
        Rolls back any unsaved rename made to entries in file_path during
        this session, when the user discards the tab instead of saving.

        mark_dirty() fires immediately after every successful .tex rewrite
        (see _rewrite_single_reference / handle_entry_table_edit /
        _sync_range_partner), independent of Save. The .tex buffer itself
        is safely deferred — Qt's own document-modified flag, restored by
        WorkspaceLifecycleController.discard_unsaved_changes on Discard —
        but until this method, nothing reverted the in-memory cache
        (EntryModifierModel._records) or the tree/table views that read
        from it, so a discarded rename kept showing in the UI even after
        the underlying .tex text and DB row were both back to their
        original, un-renamed state.

        Only entries never flushed to the DB this session reach here — an
        already-saved-and-closed tab's dirty ids were already cleared by
        flush_dirty_to_db at save time, so there's nothing left to revert
        for them. Since a still-dirty record was by definition never
        written to the DB, the DB row EntryModifierModel.revert_dirty_record
        reads back is still exactly the pre-edit baseline.
        """
        dirty_ids = self._entry_model.get_dirty_ids_for_file(file_path)
        for entry_id in dirty_ids:
            old_heading = self._entry_model.get_heading_text(entry_id)
            record = self._entry_model.get_record(entry_id) or {}
            is_closer = record.is_range_closer

            db_row = self._entry_model.revert_dirty_record(entry_id)
            if db_row is None:
                continue

            db_heading = db_row.get("heading_raw_text", "")
            self._staging_model.register_original(entry_id, db_heading)

            # Closers are never shown in the tree (see
            # _handle_manual_index_insertion) — reattaching one here would
            # spuriously make it appear for the first time. Their
            # heading_id still needs to track the reverted heading though
            # (see _reassign_closer_heading_id's docstring for why).
            if old_heading and db_heading and old_heading != db_heading:
                if is_closer:
                    self._reassign_closer_heading_id(entry_id, old_heading, db_heading)
                else:
                    self._reconcile_heading_node(entry_id, old_heading, db_heading)

            self.entry_reverted.emit(entry_id, db_heading)

    # ------------------------------------------------------------------
    # Undo/redo command execution
    # ------------------------------------------------------------------

    def apply_command(self, command) -> bool:
        r"""
        Executes one IndexCommand in the forward direction -- used for
        both undo (the caller passes ``command.inverted()``) and redo (the
        caller passes the command itself). This is the ONLY place an undo
        touches the document, so every reversal goes through the same
        primitives the original operation used and no undo path does its
        own position math.

        Order matters and mirrors the forward operations exactly:

        1. Every macro edit is applied in sequence. Each one updates its
           own entry's span and shifts every later reference in the same
           file, precisely as rewrite_macro_span's callers already do.
        2. Only then are records created or destroyed. A record must not
           exist while the shift sweep for its own insertion runs
           (shift_coordinates_after skips the entry AT the edit position,
           not one that isn't there yet), and must still exist while the
           sweep for its own deletion runs.

        Returns False without leaving a partial write behind: an edit
        whose span no longer holds the text the command recorded (the file
        was changed underneath it) aborts the whole command, rolling back
        any edits already applied. The caller leaves the stacks untouched
        in that case, so the operation stays undoable once the cause is
        resolved.
        """
        from bookindexcore.model.commands import DELETE, EDIT, INSERT

        applied: list = []
        # One adoption for the whole command, including any rollback: the
        # backend maintains its own table as each edit lands, so rebuilding it
        # per edit was redoing work the backend had just done. On a command
        # that renames every entry of a large index this is the difference
        # between usable and not -- see `bulk_writes`.
        with self.bulk_writes():
            for edit in command.edits:
                if not self._apply_macro_edit(edit):
                    self._roll_back_applied_edits(applied)
                    return False
                applied.append(edit)

        if command.kind == DELETE:
            for snapshot in command.entries:
                self._cleanup_deleted_entry(
                    snapshot.entry_id, snapshot.heading_text, snapshot.heading_id
                )
        elif command.kind == INSERT:
            for snapshot in command.entries:
                self._recreate_entry(snapshot, command)
        elif command.kind == EDIT:
            for change in command.headings:
                self._apply_heading_change(change)

        return True

    def _apply_macro_edit(self, edit) -> bool:
        r"""
        Replays one recorded span edit, then keeps every coordinate that
        depends on it in step.

        The undo/redo path, and the one place all three operations arrive
        through the same door -- a recorded edit with no ``before_text`` is
        re-inserting something a deletion removed, and one with no
        ``after_text`` is removing something an insertion added.

        **The record may not exist yet**, which is why this cannot simply call
        :meth:`_write_span`. Undoing a deletion re-writes the macro *first*
        and recreates the record afterwards (``_recreate_entry``), so there is
        nothing in the cache to look a locator up on. Placement takes the
        position from the recorded edit instead, which is exactly the case the
        anchorless locator exists for.

        Returns False without leaving a partial write behind: an edit whose
        span no longer holds what was recorded aborts, and the caller rolls
        back whatever the command had already applied.
        """
        file_path = edit.file_path
        position = edit.absolute_position

        if edit.before_text:
            record = self._entry_model.get_record(edit.entry_id)
            if record is not None:
                if not self._write_span(edit.entry_id, edit.before_text, edit.after_text):
                    return False
                return True

            # No cached record, so there is no locator to name the entry by
            # and `apply` has nothing to find. The span is still on disk, so
            # it is rewritten directly and the backend is told what moved --
            # the same "somebody else changed the text" route the injections
            # take. **The one write in this application that does not go
            # through `backend.apply`**, and it is here because identity is
            # what the backend needs and identity is exactly what a record
            # that no longer exists cannot supply.
            old_end = position + len(edit.before_text)
            current = self._doc_io.read_macro_span(file_path, position, old_end)
            if current != edit.before_text:
                print(
                    f"[UNDO GUARD] span at {position} in {os.path.basename(file_path)} "
                    f"holds {current!r}, expected {edit.before_text!r} — aborting"
                )
                return False
            delta = self._doc_io.rewrite_macro_span(
                file_path, position, old_end, edit.after_text,
                expected_macro_name=edit.command_name,
            )
            if delta is None:
                return False
            self.note_external_shift(file_path, position, delta)
            return True

        if not self.place_macro(file_path, position, edit.after_text).ok:
            return False
        return True

    def _roll_back_applied_edits(self, applied: list) -> None:
        """
        Puts back the edits of a command that failed partway. Walks them
        in reverse for the same reason IndexCommand.inverted() does: each
        edit shifted everything after it.
        """
        for edit in reversed(applied):
            if not self._apply_macro_edit(edit.inverted()):
                print(
                    "[UNDO GUARD] rollback of a partially applied command failed — "
                    f"{os.path.basename(edit.file_path)} may need a resync"
                )

    def _recreate_entry(self, snapshot, command) -> None:
        """
        Restores a record that a deletion removed: its DB row, cache
        entry, staging baseline, heading row and tree node.

        The heading may have been pruned when the last reference under it
        went away, so it is resolved (and recreated if needed) rather than
        assumed. Its id can legitimately differ from the one the snapshot
        recorded -- SQLite assigns a fresh rowid when a deleted heading is
        re-inserted -- so the restored record takes the resolved id, not
        the remembered one.
        """
        record = copy_record(snapshot.record)

        # Coordinates come from the edit that just re-wrote this entry's
        # macro, not from the snapshot: everything around it may have
        # moved between the deletion and this restore.
        for edit in command.edits:
            if edit.entry_id == snapshot.entry_id and edit.after_text:
                record.locator = record.locator.with_hint(
                    absolute_position=edit.absolute_position,
                    absolute_end=edit.absolute_end,
                )
                break

        heading_id = self._resolve_heading_for_restore(snapshot)
        if heading_id is not None:
            record.heading_id = heading_id

        self._entry_model.register_new_entry(record)

        if not snapshot.is_range_closer and snapshot.parts_list:
            # suppress_transaction: this record is being re-attached with
            # its DB row already written by register_new_entry above, not
            # staged for a first-time insert.
            self._tree.append_entry(list(snapshot.parts_list), [record], suppress_transaction=True)

    def _resolve_heading_for_restore(self, snapshot) -> int | None:
        """
        Finds or recreates the heading a restored reference belongs under,
        in the DB and in the engine's active-headings cache.
        """
        heading_text = snapshot.heading_text
        if not heading_text:
            return snapshot.heading_id

        engine = getattr(self._tree, "engine", None)
        persistence = getattr(self._entry_model, "_persistence", None)

        if engine is None:
            return (
                persistence.resolve_heading_path(heading_text)
                if persistence is not None else snapshot.heading_id
            )

        # The engine allocates the id and records the heading in
        # _active_headings in one step, so the two can no longer disagree
        # about whether a heading exists -- this used to resolve the row in
        # the DB and then patch _active_headings separately.
        heading_id = engine.resolve_heading_path(heading_text)
        return heading_id if heading_id is not None else snapshot.heading_id

    def _apply_heading_change(self, change) -> None:
        """
        Puts one entry's heading text back to a recorded value, in the
        cache, the staging baseline and the tree. The macro text itself
        was already rewritten by this command's edits.
        """
        record = self._entry_model.get_record(change.entry_id)
        if record is None:
            return

        record.heading_raw = change.after_heading
        self._staging_model.register_original(change.entry_id, change.after_heading)
        self._entry_model.mark_dirty(change.entry_id)
        self._reconcile_heading_node(
            change.entry_id, change.before_heading, change.after_heading
        )
        self.entry_reverted.emit(change.entry_id, change.after_heading)

    def _cleanup_deleted_entry(self, entry_id: int, heading_text: str, heading_id) -> None:
        """
        Shared cache/staging/view cleanup for a reference that is going
        away permanently, whether via an explicit user delete
        (handle_entry_deletion) or a session-discard rollback
        (discard_uncommitted_entry). Both callers capture heading_text/
        heading_id from the model before invoking this, since delete_record
        below removes the record those lookups depend on.

        Cache/staging cleanup happens before the orphan check below, so a
        heading with only this one reference correctly reads as having
        zero remaining records.
        """
        self._entry_model.delete_record(entry_id)
        self._staging_model.forget(entry_id)

        if heading_text:
            self._remove_reference_from_tree_display(entry_id, heading_text)

            if heading_id is not None:
                remaining = [
                    r for r in self._entry_model.all_records()
                    if r.heading_id == heading_id
                ]
                if not remaining:
                    self._remove_orphaned_heading(self._tree.engine, heading_id, heading_text)

        self.entry_deleted.emit(entry_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reconcile_heading_node(
        self,
        entry_id: int,
        old_heading: str,
        new_heading: str,
    ) -> None:
        """
        Updates the index tree and _active_headings cache after a single
        reference changes its heading text.

        Cases handled:
          1. new_heading matches an existing heading node — re-attach
             the reference's tree leaf to that node.
          2. new_heading is new — create a heading dict in _active_headings
             and insert a new tree node.
          3. old_heading node has no remaining references — remove it from
             the tree and _active_headings.

        Previously this method only patched _active_headings / the model
        cache's heading_id — it never touched the tree's own per-node ref
        list (the column-1 sibling's UserRole+1 data + "[uid]" bracket
        text), so a table-originated heading change never showed up in the
        tree: the entry stayed listed under its old node (never detached)
        and, if a brand-new node had to be created, that node was inserted
        with an empty ref list so the entry didn't appear there either.
        Detaching from the old node and attaching to the new one — via the
        same primitives handle_entry_deletion already uses for the
        detach side — closes that gap.
        """
        engine = self._tree.engine
        record = self._entry_model.get_record(entry_id)

        # Both old_heading and new_heading may carry a "|encap" suffix
        # (new_heading always does when EntryModifierController
        # ._assemble_canonical_heading built it from a row with a
        # non-empty Page/encap column; old_heading normally doesn't,
        # since EntryModifierModel's cached heading_raw_text never
        # includes it — but stripping both defensively costs nothing).
        # _active_headings' own heading_text values never include encap
        # either, so leaving it in would mean _find_heading_id_by_text
        # never matches an existing node for an encap'd heading (spawning
        # a spurious duplicate every time) and the encap literal would
        # leak into the tree node's own display label as if it were a
        # heading level.
        old_heading_clean = self._strip_encap_suffix(old_heading)
        new_heading_clean = self._strip_encap_suffix(new_heading)

        # Detach this reference from the OLD heading node's display first —
        # must happen before the heading_id reassignment below, and while
        # old_heading still names the node this entry is currently attached
        # to. Mirrors handle_entry_deletion's use of the same helper.
        self._remove_reference_from_tree_display(entry_id, old_heading_clean)

        # --- Find or create the new heading in _active_headings ---
        new_heading_id = self._find_heading_id_by_text(engine, new_heading_clean)
        if new_heading_id is None:
            new_heading_id = self._create_heading_in_engine(engine, new_heading_clean)

        # Attach this reference to the new heading's tree node, via the same
        # public incremental-insert contract IndexTreeView already exposes
        # for live single-entry inserts (append_entry). Its underlying
        # _find_or_create_row transparently finds the node if new_heading
        # already matches an existing one (case 1) or creates it fresh
        # (case 2) — either way _populate_row_metadata appends this record
        # to that node's ref list/bracket display, so the entry is never
        # left dangling under the old node or attached to a visually-empty
        # new one. append_entry (rather than calling _insert_visual_node
        # directly) also re-sorts and re-expands the tree afterward so a
        # freshly created node is immediately visible in place.
        parts = dialect.split_levels_clean(new_heading_clean)
        if parts and record:
            # suppress_transaction=True: record already exists (it's being
            # re-attached after a rename or a discard revert, not inserted
            # for the first time) -- see append_entry's docstring for why
            # this must not stage a duplicate "new entry" DB transaction.
            # The tree still stores raw payload dicts on its nodes, so it is
            # handed a row rather than the record. Phase 4 moves the tree and
            # this conversion goes with it.
            self._tree.append_entry(
                parts, [row_from_reference(record)], suppress_transaction=True
            )

        # Update the reference record's heading_id in the model cache
        if record:
            record.heading_id = new_heading_id

        # --- Check whether old heading is now orphaned ---
        old_heading_id = self._find_heading_id_by_text(engine, old_heading_clean)
        if old_heading_id is not None:
            remaining = [
                r for r in self._entry_model.all_records()
                if r.heading_id == old_heading_id
            ]
            if not remaining:
                self._remove_orphaned_heading(engine, old_heading_id, old_heading_clean)

    def _reassign_closer_heading_id(
        self,
        entry_id: int,
        old_heading: str,
        new_heading: str,
    ) -> None:
        r"""
        Discard-only counterpart to _reconcile_heading_node for range
        closers. A closer has no tree presence of its own (populate_
        hierarchy_tree never sends closers to append_entry, and
        _collect_refs_from_node's ref lists never include them), so the
        tree-attach/detach steps _reconcile_heading_node performs don't
        apply here. But its cached record["heading_id"] still needs to
        move in lockstep with its opener sibling's, or it permanently
        blocks the orphan check below (and the identical one inside
        _reconcile_heading_node): that check scans every cached record
        for a matching heading_id with no way to know a given record is
        an invisible closer, so a closer left pointing at the OLD
        heading_id keeps that heading reading as "still referenced"
        forever, even after every visible sibling has already moved off
        it via _reconcile_heading_node. That is what left a renamed-then-
        fully-discarded heading node stuck in the tree with an empty ref
        list and no way to ever be pruned -- discard_dirty_edits was
        skipping this reassignment for closers entirely.
        """
        engine = self._tree.engine
        record = self._entry_model.get_record(entry_id)
        if record is None:
            return

        old_heading_clean = self._strip_encap_suffix(old_heading)
        new_heading_clean = self._strip_encap_suffix(new_heading)

        new_heading_id = self._find_heading_id_by_text(engine, new_heading_clean)
        if new_heading_id is None:
            new_heading_id = self._create_heading_in_engine(engine, new_heading_clean)
        record.heading_id = new_heading_id

        old_heading_id = self._find_heading_id_by_text(engine, old_heading_clean)
        if old_heading_id is not None:
            remaining = [
                r for r in self._entry_model.all_records()
                if r.heading_id == old_heading_id
            ]
            if not remaining:
                self._remove_orphaned_heading(engine, old_heading_id, old_heading_clean)

    def _find_heading_id_by_text(self, engine, heading_text: str) -> int | None:
        """
        Searches _active_headings for a heading whose heading_text matches
        heading_text (case-insensitive, normalised).
        Returns the heading id if found, None otherwise.
        """
        norm = heading_text.strip().lower()
        for h in engine._active_headings:
            if h.get("heading_text", "").strip().lower() == norm:
                return h.get("id")
        return None

    def _create_heading_in_engine(self, engine, heading_text: str) -> int:
        """
        Creates a heading in _active_headings and returns its id.

        This used to allocate its own id as max(existing) + 1, making it a
        third independent assigner alongside ProjectLoadWorker's counter
        and SQLite's autoincrement. It now defers to the engine, which is
        the single allocator -- so an id handed out here can no longer
        collide with one handed out for a live insertion between saves.
        """
        return engine.resolve_heading_id(heading_text)

    def _remove_orphaned_heading(
        self, engine, heading_id: int, heading_text: str
    ) -> None:
        """
        Removes an orphaned heading from _active_headings and removes its
        node from the index tree.

        Shared by two callers: _reconcile_heading_node (a rename left the
        old heading with zero remaining references) and
        handle_entry_deletion (a deleted reference was the last one under
        its heading). Both cases mean the same thing at this point — no
        reference anywhere still points to heading_id — so the DB row is
        cleaned up here too, via EntryModifierModel.delete_heading_if_orphaned,
        rather than in each caller separately.
        """
        engine._active_headings = [
            h for h in engine._active_headings if h.get("id") != heading_id
        ]

        # Remove the tree node — find it by ToolTipRole token match
        parts = dialect.split_levels_clean(heading_text)
        if parts:
            self._remove_tree_node_by_path(parts)

        engine.mark_heading_deleted(heading_id)

    def _remove_reference_from_tree_display(self, entry_id: int, heading_text: str) -> None:
        """
        Removes entry_id from the ref-list (UserRole+1) stored on the
        column-1 sibling of the tree node matching heading_text, and
        refreshes the displayed "[id] [id]" bracket text accordingly.

        Does not touch node structure — orphan-node pruning is a separate
        decision made by the caller (handle_entry_deletion) once it has
        confirmed no records remain under that heading_id, via
        _remove_orphaned_heading.
        """
        parts = dialect.split_levels_clean(heading_text)
        if not parts:
            return

        node = self._find_tree_node_by_path(parts)
        if node is None:
            return

        parent = node.parent() or self._tree.base_model.invisibleRootItem()
        sibling_col1 = parent.child(node.row(), 1)
        if sibling_col1 is None:
            return

        role_uid = Qt.ItemDataRole.UserRole + 1
        stored = sibling_col1.data(role_uid) or []
        if not isinstance(stored, list):
            return

        remaining = [
            r for r in stored
            if _ref_entry_id(r) != entry_id
        ]
        sibling_col1.setData(remaining, role_uid)
        # **One answer, not two.** This string was composed here and inside
        # the tree; step 9b made render_reference_column the single place it
        # is built, which is what lets a host that supplies no per-reference
        # label have its references numbered instead.
        sibling_col1.setText(self._tree.render_reference_column(remaining))

    def _find_tree_node_by_path(self, parts: list[str]) -> QStandardItem | None:
        """
        Walks the tree by ToolTipRole token matching (same traversal used
        by _remove_tree_node_by_path) and returns the leaf node for parts,
        or None if the path doesn't exist.
        """
        parent = self._tree.base_model.invisibleRootItem()
        node = None
        for token in parts:
            found = None
            for row in range(parent.rowCount()):
                child = parent.child(row, 0)
                if child and child.data(Qt.ItemDataRole.ToolTipRole).strip().lower() == token.lower():
                    found = child
                    break
            if found is None:
                return None
            node = found
            parent = found
        return node

    def _remove_tree_node_by_path(self, parts: list[str]) -> None:
        r"""
        Walks the tree by ToolTipRole token matching and removes the leaf
        node for the given path — but ONLY if that node has no children.

        A node can become "orphaned" (no references of its own) while
        still being a live intermediate heading — e.g. "Sports" has no
        direct \index{Sports} reference left, but "Sports!Football" is
        still a child row under it in the tree. QStandardItemModel's
        removeRow deletes a row's entire child subtree along with it, so
        removing "Sports" in that case would silently delete "Football"
        and everything under it too — the same kind of hierarchy gap the
        table-side validation guards against, just approached from the
        deletion direction instead of the edit direction. When that's the
        case, the node is left in place as a structural placeholder (its
        own ref-list cell has already been cleared by the caller); parent
        nodes are otherwise left intact regardless (they may have other
        children).
        """
        parent = self._tree.base_model.invisibleRootItem()
        for depth, token in enumerate(parts):
            found = None
            for row in range(parent.rowCount()):
                child = parent.child(row, 0)
                if child and child.data(Qt.ItemDataRole.ToolTipRole).strip().lower() == token.lower():
                    found = child
                    break
            if found is None:
                return  # path not found — tree already clean
            if depth == len(parts) - 1:
                # This is the leaf — remove it, unless it still has children.
                if found.rowCount() > 0:
                    return
                parent.removeRow(found.row())
                return
            parent = found

    def _restore_item_text(self, item: QStandardItem, original_text: str) -> None:
        """Restores the item display text and clears the pre-edit stash."""
        self._rewriting = True
        try:
            item.setText(original_text)
            item.setData(None, Qt.ItemDataRole.UserRole + 10)
        finally:
            self._rewriting = False
