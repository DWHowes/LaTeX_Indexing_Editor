r"""
Check Index — the LaTeX application's reader for the shared rule set.

The rules themselves are in ``bookindexcore.checks`` and know nothing about
LaTeX: "these two headings differ only by a plural" is a statement about index
content. What this controller supplies is the three things only an application
can: the entries, the project's vocabulary, and **document order**.

The last of those is why this file is longer than a wrapper. A ``Locator`` is
opaque to shared code, so the only sanctioned way to order two entries is
``DocumentBackend.order_key`` — and for this backend that resolves an anchor
through a per-container entry table which is only correct once the container
has been adopted. Handing over an unadopted backend would not fail: every
entry would order as ``-1``, the overlapping-range rule would find nothing,
and a clean report would be indistinguishable from one that could not look.
So :meth:`_prepare_order` adopts first, and the check runs with a
``skip_unsatisfiable`` of False so that anything still missing raises.

**Nothing here writes.** Most of what Check Index finds has no mechanical
repair — being told two headings disagree does not say which is right — so
this reports, and the indexer corrects in the editing surfaces that already
have validation and undo.
"""

from PySide6.QtWidgets import QMessageBox

from bookindexcore.checks import check_index
from bookindexcore.ui.findings_dialog import FindingsDialog

from models.latex_dialect import LATEX_DIALECT as dialect


class CheckIndexController:
    """
    Runs the shared rule set over this project and shows what it found.

    A plain object, following the precedent ``BulkRepairController`` set: it
    has no signals of its own, and the dialog it builds is parented to the
    window passed to :meth:`run` rather than owned here.
    """

    def __init__(self, entry_model, text_backend, prefs, prefs_config=None):
        self._entry_model = entry_model
        self._backend = text_backend
        self._prefs = prefs
        # The project, for the declarations that depend on one --
        # max_entry_length is per *engine* in LaTeX, so a rule that reads it
        # needs to know which engine this project selected.
        self._prefs_config = prefs_config
        self._dialog = None

    # -- gathering ----------------------------------------------------------

    def _records(self) -> list:
        """
        Every cached record with a heading.

        From the store rather than by re-reading the files, for the reason
        every tool here does it: after a project loads, the store is the truth,
        and a rename made this session but not yet saved is in the store and
        not yet on disk.
        """
        return [record for record in self._entry_model.all_records()
                if record.heading_raw]

    def _prepare_order(self, records):
        """
        Make ``backend.order_key`` answerable for these records, and return it.

        Adoption is what aligns the backend's table with the anchors this
        application's database is keyed by. Without it ``_find`` reports that
        no such entry exists and ``order_key`` returns ``-1`` for everything —
        which is not an error anybody sees, just an ordering in which nothing
        ever overlaps.
        """
        containers = {record.locator.container for record in records
                      if record.locator.container}
        for container in containers:
            self._backend.adopt_entries(container, records)
        return self._backend.order_key

    # -- running ------------------------------------------------------------

    def findings(self) -> list:
        """
        What the enabled rules have to say about this project.

        Separate from :meth:`run` so the interesting half is testable without
        driving a dialog — the same split ``ChangeSet``/``PreviewDialog`` made
        in E2, and for the same reason.
        """
        records = self._records()
        if not records:
            return []
        return check_index(
            records,
            dialect=dialect,
            grammar=self._prefs.grammar(),
            project=self._prefs_config,
            order_key=self._prepare_order(records),
            enabled=self._prefs.enabled_rules(),
        )

    def run(self, parent_window=None) -> int:
        """
        Check the index and show the report. Returns how many findings there
        were.

        The dialog is **non-modal and held**, so it can stay open beside the
        entry table while the indexer works through it. Held on the controller
        rather than left to Qt's garbage collector, because a non-modal dialog
        nobody holds a reference to closes itself the moment this method
        returns.
        """
        found = self.findings()
        if not found:
            QMessageBox.information(
                parent_window, "Check index",
                "Nothing to report: every check this project has switched on "
                "is satisfied.")
            return 0

        self._dialog = FindingsDialog(found, parent=parent_window)
        self._dialog.show()
        return len(found)

    @property
    def dialog(self):
        """The open report, or None. Exposed so the application can theme it."""
        return self._dialog
