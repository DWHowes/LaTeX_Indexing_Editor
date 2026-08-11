r"""
Bulk entry repair — the first tool built on the preview-and-apply contract.

The syntax checker has been able to repair a field mechanically since it was
written (``index_syntax_check.apply_fixes``), but only one field at a time, in
the entry window, while somebody is looking at it. Nothing has ever offered to
do it across a whole index — so a project that accumulated the same fault a
hundred times had to be corrected a hundred times by hand.

This is that offer, and it is deliberately the *smallest* tool that exercises
the whole path: find what could change, propose it, let the indexer approve a
subset, and apply that subset as **one undoable command**. Everything the
expansion's larger tools need is here at a size where it can be read.

**What it will not do.** Only repairs the checker already knows how to make,
and only those it can make mechanically — a finding with no fix is one that
needs a person, and this passes over it silently rather than guessing. It
never touches a heading whose repair would change what the heading *says*:
every fix here is about characters the index engine will misread, not about
wording.
"""

from PySide6.QtWidgets import QMessageBox

from bookindexcore.model.commands import MacroEdit, edit_command
from bookindexcore.model.proposals import ChangeSet, ProposedChange
from bookindexcore.ui.preview_dialog import PreviewDialog

from models import index_syntax_check as syntax
from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT as dialect
from models.latex_record_mapping import command_of, end_of, position_of


class BulkRepairController:
    r"""
    Proposes every mechanical repair the checker can make across the index,
    and applies the approved ones as a single command.

    Holds no state of its own: the entry store is the truth about what exists,
    and the command it builds is handed to ``IndexEditController`` to apply,
    which is what puts it on the undo stack as one step.

    **A plain object, not a QObject.** It has no signals and no slots, and the
    only thing a Qt parent would buy is lifetime, which the application's own
    attribute reference already provides. ``SessionLogger`` was demoted for
    exactly this reason and the precedent is worth following. The modal parent
    the preview needs is passed to :meth:`run`, which is a different thing
    from ownership.
    """

    def __init__(self, entry_model, index_edit_ctrl, doc_io):
        self._entry_model = entry_model
        self._index_edit_ctrl = index_edit_ctrl
        self._doc_io = doc_io

    # -- proposing ----------------------------------------------------------

    def propose(self) -> ChangeSet:
        r"""
        What repairing the whole index would change.

        Works from the **cached records** rather than by re-reading the files,
        for the same reason every other tool here does: the store is the truth
        after a project is loaded, and a rename made this session but not yet
        saved is in the store and not yet on disk.

        Each heading is taken apart into its levels by the dialect, repaired a
        level at a time, and put back together. That is not tidiness: the
        checker's contract is that it is given **one field**, because ``!`` and
        ``|`` are ordinary characters inside a level and separators between
        them. Handing it a whole heading would have it report every separator
        in the entry as a fault.
        """
        changes: list[ProposedChange] = []

        for record in self._entry_model.all_records():
            heading = record.heading_raw or ""
            if not heading:
                continue

            repaired = self._repair_heading(heading)
            if repaired == heading:
                continue

            changes.append(ProposedChange(
                key=record.entry_id,
                label=dialect.display_of(dialect.level_path(heading)[-1])
                if dialect.level_path(heading) else heading,
                before=heading,
                after=repaired,
                note=self._why(heading),
            ))

        return ChangeSet.of(
            "Repair index entries",
            changes,
            prompt=(
                "These entries contain characters the index engine will misread. "
                "Each repair below is mechanical — it changes how the entry is "
                "written, never what it says. Untick anything you would rather "
                "fix yourself."
            ),
        )

    @staticmethod
    def _repair_heading(heading: str) -> str:
        """One heading, repaired a level at a time and rejoined."""
        levels = dialect.split_levels(heading)
        return dialect.join_levels(
            syntax.apply_fixes(level, role=syntax.ROLE_DISPLAY) for level in levels
        )

    @staticmethod
    def _why(heading: str) -> str:
        """
        A short reason, taken from the first fixable finding.

        One reason rather than all of them: the column is a hint about why a
        row is here, and an indexer deciding about a row wants to recognise
        the problem, not to read a report about it.
        """
        for level in dialect.split_levels(heading):
            for finding in syntax.check(level, role=syntax.ROLE_DISPLAY):
                if finding.has_fix:
                    return finding.message.split(".")[0].strip()
        return ""

    # -- applying -----------------------------------------------------------

    def build_command(self, approved: list[ProposedChange]):
        r"""
        The approved repairs, as one ``IndexCommand``.

        Returns None when there is nothing to do, so a caller can tell "the
        indexer approved nothing" from "the command failed" without inspecting
        an empty command.

        Every edit is built from the record's **current** coordinates and the
        macro **as it is on disk**, not from anything captured when the
        proposal was made. A preview can sit open while the indexer thinks,
        and an entry can move underneath it in that time; rebuilding here
        means the edits describe the document as it is at the moment of
        applying, and the backend's own guard refuses any that still do not
        match.
        """
        edits = []
        for change in approved:
            record = self._entry_model.get_record(change.key)
            if record is None:
                continue

            start, end = position_of(record), end_of(record)
            container = record.locator.container
            if start is None or end is None or not container:
                continue

            current = self._doc_io.read_macro_span(container, start, end)
            if not current:
                continue

            command_name = command_of(record)
            new_macro = grammar.build_macro(
                self._rebuilt_body(current, change.after),
                command=command_name,
                index_class=grammar.index_class_of(
                    current, grammar.command_pattern(command_name)),
            )
            if new_macro == current:
                continue

            edits.append(MacroEdit(
                change.key, container, start, current, new_macro, command_name))

        if not edits:
            return None
        return edit_command(f"Repair {len(edits)} index entries", edits, [])

    @staticmethod
    def _rebuilt_body(current_macro: str, repaired_heading: str) -> str:
        r"""
        The repaired heading with this entry's own encapsulation re-attached.

        The encapsulation is read back off the macro on disk rather than taken
        from the record, and that is a lesson rather than a preference:
        ``heading_raw`` never carries the ``|encap`` suffix, so rebuilding a
        macro from the heading alone silently **deletes** it — turning
        ``\index{Main|textbf}`` into ``\index{Main}`` and, worse, dropping the
        ``|(`` that opens a page range. The rename path learned this the hard
        way and reads it back for the same reason.
        """
        parsed = grammar.parse_macro(current_macro)
        encap = parsed.encap if parsed else ""
        return f"{repaired_heading}|{encap}" if encap else repaired_heading

    # -- the whole flow -----------------------------------------------------

    def run(self, parent_window=None) -> int:
        """
        Propose, preview, and apply what was approved. Returns how many
        repairs were made.

        Nothing is written unless the indexer accepts the dialog *and* has
        something ticked, and what is written goes on the undo stack as one
        step — so the worst outcome of running this by accident is one Undo.
        """
        change_set = self.propose()
        if not change_set:
            QMessageBox.information(
                parent_window, "Repair index entries",
                "Nothing to repair: no entry contains a character the index "
                "engine would misread.")
            return 0

        dialog = PreviewDialog(change_set, parent_window)
        dialog.exec()

        approved = dialog.approved()
        if not approved:
            return 0

        command = self.build_command(approved)
        if command is None:
            return 0

        if not self._index_edit_ctrl.apply_command(command):
            QMessageBox.warning(
                parent_window, "Repair index entries",
                "The repairs could not be applied and nothing has been "
                "changed. The document may have been edited since the preview "
                "was taken; try again.")
            return 0

        # Recorded so it can be undone in one step, like any other edit.
        self._index_edit_ctrl.command_recorded.emit(command)
        return len(command.edits)
