r"""
Bulk entry repair — the first tool on the preview-and-apply contract.

Driven end to end against a real stack: a real ``.tex`` file, a real parse,
a real rewrite through ``backend.apply``. The dialog itself is not driven --
this suite's convention is not to run modal machinery -- so ``propose``,
``build_command`` and ``apply_command`` are exercised directly, which is
exactly what ``run`` strings together.

The properties that matter are the ones §3.3 of the assessment demands of
every tool that changes anything:

  approved subset   -- what the indexer ticked, and nothing else
  one command       -- one step on the undo stack, however many entries
  reversible        -- inverting restores the file byte for byte
"""

from PySide6.QtWidgets import QTabWidget

from bookindexcore.model.proposals import ProposedChange
from bookindexcore.qt.staging import QtIndexEditStagingModel
from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.util.text import TextSanitizer

from controllers.bulk_repair_controller import BulkRepairController
from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from models.entry_modifier_model import EntryModifierModel
from models.latex_index_parser import LatexIndexParser
from views.index_tree_view import IndexTreeView


class _FakeEngine:
    def __init__(self):
        self._active_headings = []

    def mark_heading_deleted(self, heading_id):
        pass


def _stack(tmp_path, qtbot, tex):
    path = tmp_path / "chapter.tex"
    path.write_text(tex, encoding="utf-8")

    tree = IndexTreeView(model_engine=_FakeEngine())
    qtbot.addWidget(tree)
    staging = QtIndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging)
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
    index_edit = IndexEditController(
        tree_view=tree, doc_io=doc_io,
        entry_modifier_model=entry_model, staging_model=staging)

    payloads, _ = LatexIndexParser.parse_file(str(path))
    entry_model.load_records([{
        "unique_id_number": uid["unique_id_number"],
        "heading_raw_text": "!".join(parts),
        "uid": uid["uid"],
        "file_path": str(path),
        "line_number": uid["line_number"],
        "column_offset": uid["column_offset"],
        "absolute_position": uid["absolute_index"],
        "absolute_end": uid["end_absolute_index"] + 1,
        "encap": uid["encap"],
        "macro_command": uid["macro_command"],
        "see_references": None, "seealso_references": None,
    } for parts, uid in payloads])

    repair = BulkRepairController(entry_model, index_edit, doc_io)
    return repair, index_edit, entry_model, path


class TestProposing:
    def test_it_finds_entries_the_engine_would_misread(self, tmp_path, qtbot):
        repair, *_ = _stack(tmp_path, qtbot, "x \\index{Cats & dogs} y\n")

        proposal = repair.propose()

        assert len(proposal) == 1
        assert proposal.changes[0].after == r"Cats \& dogs"

    def test_a_clean_index_proposes_nothing(self, tmp_path, qtbot):
        repair, *_ = _stack(
            tmp_path, qtbot,
            "x \\index{Cats} y \\index{Dogs!Terriers} z\n")

        assert not repair.propose()

    def test_each_level_is_repaired_separately(self, tmp_path, qtbot):
        r"""
        The checker's contract is that it is given ONE field: ``!`` and ``|``
        are ordinary characters inside a level and separators between them, so
        handing it a whole heading would have it report every separator in the
        entry as a fault.
        """
        repair, *_ = _stack(tmp_path, qtbot, "x \\index{Cats & dogs!Food & water} y\n")

        change = repair.propose().changes[0]

        assert change.after == r"Cats \& dogs!Food \& water"
        assert change.after.count("!") == 1        # the separator survived

    def test_it_says_why(self, tmp_path, qtbot):
        repair, *_ = _stack(tmp_path, qtbot, "x \\index{Cats & dogs} y\n")
        assert repair.propose().changes[0].note

    def test_a_finding_with_no_mechanical_fix_is_passed_over(self, tmp_path, qtbot):
        """
        An unclosed brace still needs a person. Proposing a repair the checker
        cannot actually make would be guessing at what the indexer meant.
        """
        repair, *_ = _stack(tmp_path, qtbot, "x \\index{Cats {unclosed} y\n")
        assert not repair.propose()

    def test_a_legal_character_is_left_alone(self, tmp_path, qtbot):
        r"""
        ``~`` is a non-breaking space in LaTeX, not an error, so escaping it
        would change what the entry *means* rather than how it is written --
        which is the line this tool does not cross. The checker offers no fix
        for it and neither does this.
        """
        repair, *_ = _stack(tmp_path, qtbot, "x \\index{Birds ~ nests} y\n")
        assert not repair.propose()


class TestApplyingTheApprovedSubset:
    def _proposal_for(self, tmp_path, qtbot):
        # Three characters that each carry a mechanical fix. Deliberately not
        # "~": it is a legal LaTeX tie, so escaping it would change what the
        # entry means -- and the checker rightly offers no fix for it.
        tex = ("a \\index{Cats & dogs} b \\index{Birds # nests} "
               "c \\index{Fish % scales} d\n")
        repair, index_edit, entry_model, path = _stack(tmp_path, qtbot, tex)
        return repair, index_edit, entry_model, path, repair.propose()

    def test_only_the_approved_changes_are_written(self, tmp_path, qtbot):
        """
        The point of returning a subset rather than a yes/no: an indexer takes
        two of three and fixes the other by hand.
        """
        repair, index_edit, _model, path, proposal = self._proposal_for(tmp_path, qtbot)
        approved = [c for c in proposal.changes if "Fish" not in c.before]
        assert len(approved) == 2

        command = repair.build_command(approved)
        assert index_edit.apply_command(command)

        text = path.read_text(encoding="utf-8")
        assert r"Cats \& dogs" in text
        assert r"Birds \# nests" in text
        assert "Fish % scales" in text        # untouched, as asked

    def test_it_is_one_command_whatever_it_carries(self, tmp_path, qtbot):
        repair, _idx, _model, _path, proposal = self._proposal_for(tmp_path, qtbot)

        command = repair.build_command(list(proposal.changes))

        assert len(command.edits) == 3
        assert command.label == "Repair 3 index entries"

    def test_approving_nothing_builds_no_command(self, tmp_path, qtbot):
        """
        None rather than an empty command, so a caller can tell "the indexer
        approved nothing" from "the command failed".
        """
        repair, *_ = self._proposal_for(tmp_path, qtbot)
        assert repair.build_command([]) is None

    def test_undoing_restores_the_file_byte_for_byte(self, tmp_path, qtbot):
        repair, index_edit, _model, path, proposal = self._proposal_for(tmp_path, qtbot)
        original = path.read_text(encoding="utf-8")

        command = repair.build_command(list(proposal.changes))
        assert index_edit.apply_command(command)
        assert path.read_text(encoding="utf-8") != original

        assert index_edit.apply_command(command.inverted())
        assert path.read_text(encoding="utf-8") == original


class TestWhatItRefusesToLose:
    def test_a_page_style_survives_the_repair(self, tmp_path, qtbot):
        r"""
        ``heading_raw`` never carries the ``|encap`` suffix, so rebuilding a
        macro from the heading alone silently deletes it. The rename path
        learned this the hard way; this reads the encapsulation back off the
        macro on disk for the same reason.
        """
        repair, index_edit, _m, path = _stack(
            tmp_path, qtbot, "x \\index{Cats & dogs|textbf} y\n")

        command = repair.build_command(list(repair.propose().changes))
        assert index_edit.apply_command(command)

        assert r"\index{Cats \& dogs|textbf}" in path.read_text(encoding="utf-8")

    def test_a_range_marker_survives_the_repair(self, tmp_path, qtbot):
        r"""
        Worse than losing a style: dropping the ``|(`` destroys the page range
        along with it, and the closer is left orphaned.
        """
        repair, index_edit, _m, path = _stack(
            tmp_path, qtbot, "x \\index{Cats & dogs|(} y \\index{Cats & dogs|)} z\n")

        command = repair.build_command(list(repair.propose().changes))
        assert index_edit.apply_command(command)

        text = path.read_text(encoding="utf-8")
        assert r"\index{Cats \& dogs|(}" in text
        assert r"\index{Cats \& dogs|)}" in text

    def test_an_index_class_survives_the_repair(self, tmp_path, qtbot):
        r"""
        The class sits outside the braces and so is not in the heading either.
        Dropping it would move the entry out of its named index into the
        default one -- silently, and only visible in the finished book.
        """
        repair, index_edit, _m, path = _stack(
            tmp_path, qtbot, "x \\index[names]{Cats & dogs} y\n")

        command = repair.build_command(list(repair.propose().changes))
        assert index_edit.apply_command(command)

        assert r"\index[names]{Cats \& dogs}" in path.read_text(encoding="utf-8")

    def test_a_stale_proposal_is_refused_rather_than_misapplied(self, tmp_path, qtbot):
        """
        A preview can sit open while the indexer thinks, and the document can
        move underneath it. Edits are rebuilt from current coordinates at
        apply time, and the backend's guard refuses any that still do not
        match -- so the outcome is nothing written, not the wrong span
        rewritten.
        """
        repair, index_edit, _model, path = _stack(
            tmp_path, qtbot, "x \\index{Cats & dogs} y\n")
        proposal = repair.propose()

        # Something else edits the file underneath the open preview.
        path.write_text("completely different content\n", encoding="utf-8")

        command = repair.build_command(list(proposal.changes))
        if command is not None:
            assert index_edit.apply_command(command) is False


class TestKeyingBackToRecords:
    def test_a_change_whose_entry_has_gone_is_skipped(self, tmp_path, qtbot):
        """
        Proposals carry the entry id rather than a position, so an entry
        deleted between preview and apply drops out instead of being matched
        by index to whatever now sits in its place.
        """
        repair, _idx, entry_model, _path = _stack(
            tmp_path, qtbot, "x \\index{Cats & dogs} y\n")
        proposal = repair.propose()

        assert repair.build_command([
            ProposedChange(key=99_999, label="gone", before="a", after="b")
        ]) is None
        assert len(proposal.changes) == 1
