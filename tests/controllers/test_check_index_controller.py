r"""
Check Index — the LaTeX application's reader for the shared rule set.

Driven against a real stack: a real ``.tex`` file, a real parse, real
records, the real backend. The rules themselves are tested in
``bookindexcore``, against a dialect no file is written in, precisely so
that nothing about them can be LaTeX; what is tested here is the three
things only an application can supply, and one of them is the reason this
file exists.

**Document order is the one that can fail silently.** ``order_key`` resolves
an anchor through a per-container entry table, and against an unadopted
backend it answers ``-1`` for every entry: no exception, no warning, and an
overlapping-range rule that finds nothing because it could not look. That is
the same shape as the bug this project already shipped once, so
``TestDocumentOrder`` pins it rather than trusting it.
"""

from PySide6.QtWidgets import QTabWidget

from bookindexcore.checks import ALL_RULES
from bookindexcore.qt.staging import QtIndexEditStagingModel
from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.util.text import TextSanitizer

from controllers.check_index_controller import CheckIndexController
from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from controllers.latex_text_backend import LatexTextBackend
from models.check_index_prefs import (
    CHECK_INDEX_DEFAULTS, DISABLED_RULES_KEY, CheckIndexPrefs,
)
from models.entry_modifier_model import EntryModifierModel
from models.latex_index_parser import LatexIndexParser
from views.index_tree_view import IndexTreeView


class _FakeEngine:
    def mark_heading_deleted(self, heading_id):
        pass


def _paired(rows):
    r"""
    FIFO range pairing, as ``ProjectLoadWorker`` does it at project load.

    Done here because the parser does not: it reports each ``\index`` macro
    as it finds it, and which ``|)`` closes which ``|(`` is worked out
    afterwards. A fixture that skipped this would leave every opener with no
    partner, and the overlapping-range rule -- which needs both ends of a
    span -- would have nothing to look at while appearing to pass.
    """
    open_by_heading = {}
    for row in rows:
        encap, heading = row["encap"] or "", row["heading_raw_text"]
        if encap.endswith("(") or encap.startswith("("):
            open_by_heading.setdefault(heading, []).append(row)
        elif encap.endswith(")") or encap.startswith(")"):
            waiting = open_by_heading.get(heading) or []
            if waiting:
                opener = waiting.pop(0)
                opener["range_partner_id"] = row["unique_id_number"]
                row["range_partner_id"] = opener["unique_id_number"]
    return rows


def _stack(tmp_path, qtbot, tex, prefs=None):
    path = tmp_path / "chapter.tex"
    path.write_text(tex, encoding="utf-8")

    tree = IndexTreeView(model_engine=_FakeEngine())
    qtbot.addWidget(tree)
    staging = QtIndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging)
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
    backend = LatexTextBackend(doc_io)
    # Built only so the stack matches the running application's; nothing here
    # writes, which is the whole character of this tool.
    IndexEditController(tree_view=tree, doc_io=doc_io,
                        entry_modifier_model=entry_model, staging_model=staging)

    payloads, _ = LatexIndexParser.parse_file(str(path))
    entry_model.load_records(_paired([{
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
    } for parts, uid in payloads]))

    controller = CheckIndexController(
        entry_model, backend, prefs or CheckIndexPrefs())
    return controller, entry_model, backend, path


def rules(findings):
    return {finding.rule for finding in findings}


class TestItRunsOverARealProject:

    def test_a_consistent_index_reports_nothing(self, tmp_path, qtbot):
        """
        The property that decides whether anybody uses this. Two dozen
        similarity detectors over a sound index have to be silent, or the
        first real run buries its one true finding in noise.
        """
        controller, *_ = _stack(tmp_path, qtbot, (
            "a \\index{Costs!appeal} b \\index{Costs!taxation} c\n"
            "d \\index{Damages} e \\index{Evidence, documentary} f\n"
            "g \\index{Evidence, oral} h \\index{Fraud} i\n"))
        assert controller.findings() == []

    def test_it_finds_headings_that_disagree(self, tmp_path, qtbot):
        controller, *_ = _stack(
            tmp_path, qtbot, "a \\index{Trial} b \\index{Trials} c\n")
        assert rules(controller.findings()) == {"headings.plural"}

    def test_it_finds_a_cross_reference_with_no_target(self, tmp_path, qtbot):
        controller, *_ = _stack(tmp_path, qtbot, (
            "a \\index{Costs} b \\index{Fees|see{Expenses}} c\n"))
        found = controller.findings()
        assert "references.missing_target" in rules(found)
        assert any(f.is_error for f in found)

    def test_an_empty_project_is_not_an_error(self, tmp_path, qtbot):
        controller, *_ = _stack(tmp_path, qtbot, "nothing here\n")
        assert controller.findings() == []

    def test_the_findings_name_entries_that_exist(self, tmp_path, qtbot):
        """
        A report that points at nothing is a report an indexer cannot act on,
        and an id that no longer resolves is exactly how that happens.
        """
        controller, entry_model, *_ = _stack(
            tmp_path, qtbot, "a \\index{Trial} b \\index{Trials} c\n")
        for finding in controller.findings():
            for entry_id in finding.entry_ids:
                assert entry_model.get_record(entry_id) is not None


class TestDocumentOrder:

    def test_the_backend_can_order_every_entry_it_is_given(
            self, tmp_path, qtbot):
        r"""
        The silent failure this guards. ``order_key`` resolves an anchor
        through the backend's per-container table; against an unadopted
        backend it returns ``-1`` for everything, the range rules find no
        overlaps, and a report that could not look is indistinguishable from
        a clean one. The controller adopts first — so every key here must be
        a real position.
        """
        controller, entry_model, backend, _ = _stack(tmp_path, qtbot, (
            "a \\index{Costs|(} b \\index{Costs|)} c\n"))
        records = list(entry_model.all_records())

        order = controller._prepare_order(records)
        keys = [order(record.locator) for record in records]

        assert all(key >= 0 for key in keys), keys
        assert keys == sorted(keys)

    def test_without_adoption_the_keys_are_all_the_same(
            self, tmp_path, qtbot):
        """
        The other half of the pin: this is what the report would look like if
        the controller stopped adopting. Recorded as a test so that a change
        which drops the adoption fails here rather than quietly producing an
        index in which nothing ever overlaps.
        """
        _, entry_model, backend, _ = _stack(tmp_path, qtbot, (
            "a \\index{Costs|(} b \\index{Costs|)} c\n"))
        records = list(entry_model.all_records())

        assert {backend.order_key(r.locator) for r in records} == {-1}

    def test_overlapping_ranges_are_reachable_at_all(self, tmp_path, qtbot):
        r"""
        Two ranges under one heading that cover the same pages. The rule is
        tested properly in the core; what this proves is that a real LaTeX
        project can reach it — which needs the adoption above to have worked.
        """
        controller, *_ = _stack(tmp_path, qtbot, (
            "a \\index{Costs|(} b \\index{Costs|(} c "
            "\\index{Costs|)} d \\index{Costs|)} e\n"))
        assert "locators.overlapping_ranges" in rules(controller.findings())


class TestTheProjectsOwnVocabulary:

    def test_latex_words_are_exempt_from_the_mixed_case_rule(
            self, tmp_path, qtbot):
        r"""
        The application's contribution to a shared rule. Nothing about
        ``LaTeX``'s shape distinguishes it from a typing slip, so no
        heuristic in the core can exempt it — somebody who knows what the
        project is about has to say, and for this application that is the
        seeded exception list.
        """
        controller, *_ = _stack(
            tmp_path, qtbot, "a \\index{LaTeX} b \\index{BibTeX} c\n")
        assert "basic.mixed_case" not in rules(controller.findings())

    def test_a_real_slip_is_still_reported(self, tmp_path, qtbot):
        controller, *_ = _stack(
            tmp_path, qtbot, "a \\index{enGland} b\n")
        assert "basic.mixed_case" in rules(controller.findings())

    def test_a_general_cross_reference_is_not_a_dangling_one(
            self, tmp_path, qtbot):
        controller, *_ = _stack(tmp_path, qtbot, (
            "a \\index{Costs} b \\index{Diseases|see{specific diseases}} c\n"))
        assert "references.missing_target" not in rules(controller.findings())


class TestTheRuleSelection:

    def test_by_default_everything_but_the_opt_in_rule_runs(self):
        prefs = CheckIndexPrefs()
        expected = {rule.id for rule in ALL_RULES} - {
            "locators.above_lowest_level"}
        assert prefs.enabled_rules() == expected

    def test_a_project_can_switch_a_rule_off(self, tmp_path, qtbot):
        prefs = CheckIndexPrefs(
            {DISABLED_RULES_KEY: ["headings.plural"]})
        controller, *_ = _stack(
            tmp_path, qtbot, "a \\index{Trial} b \\index{Trials} c\n",
            prefs=prefs)
        assert controller.findings() == []

    def test_the_stored_value_is_what_is_off_not_what_is_on(self):
        r"""
        Deliberate, and the reason is a failure that would be invisible: were
        the *enabled* set stored, a rule added in a later version would be
        absent from every project's list and would arrive switched off, in
        every existing project, with nothing to see. So a project stores its
        exceptions and everything else is on.
        """
        prefs = CheckIndexPrefs()
        prefs.set_enabled_rules({"headings.plural"})
        stored = prefs.load()[DISABLED_RULES_KEY]

        assert "headings.plural" not in stored
        assert len(stored) == len(ALL_RULES) - 1

    def test_an_id_that_no_longer_names_a_rule_is_harmless(self):
        """
        So that removing a rule in a later version needs no migration.
        """
        prefs = CheckIndexPrefs({DISABLED_RULES_KEY: ["headings.retired"]})
        assert prefs.enabled_rules() == {rule.id for rule in ALL_RULES}

    def test_the_defaults_seed_the_latex_exception_list(self):
        assert "LaTeX" in CHECK_INDEX_DEFAULTS["mixed_case_exceptions"]
