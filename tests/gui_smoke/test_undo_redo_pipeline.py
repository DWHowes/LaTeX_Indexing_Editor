r"""
Undo/redo end to end, through the real booted app.

This is the regression net for the worst defect this project has had: two
independent undo systems that each assumed they were the only one. Qt's
QTextDocument undo reversed the last *document* edit, whatever it happened
to be, while a separate stack held only insertions and reversed only the
tree node -- never the DB row, never the coordinates. The two could
half-reverse different operations in the same keystroke, and checksums
structurally could not catch any of it: an undo that restores the buffer
writes the file back byte-identical, so the drift check sees no change and
never offers the resync that would repair the database.

Every class below pins one of the four documented consequences, plus the
range-pair case and the guard. They are written against the real app
(EditorTab, IndexEditController, the DB) rather than a stub, because the
whole point is that the .tex text, the DB row, the in-memory cache, the
coordinates and the tree all move together.

Ctrl+Z is delivered as a real key event wherever it is the thing under
test, so the wiring itself (EditorTab.keyPressEvent -> undo_performed ->
AppPipelineController) is covered and not just the handler.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """See test_auto_resync_safety.py's fixture of the same name -- same
    module-scoped-booted_app leakage risk applies here."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()
    pipeline_ctrl._index_commands.clear()
    for i in range(pipeline_ctrl.window.tabs.count()):
        tab = pipeline_ctrl.window.tabs.widget(i)
        if hasattr(tab, "document"):
            tab.document().setModified(False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_tab(pipeline_ctrl, file_path):
    pipeline_ctrl.handle_file_activation_request(str(file_path))
    return pipeline_ctrl.window.tabs.currentWidget()


def _open_tab_at_start(pipeline_ctrl, file_path):
    tab = _open_tab(pipeline_ctrl, file_path)
    cursor = tab.textCursor()
    cursor.setPosition(0)
    tab.setTextCursor(cursor)
    return tab


from models.latex_record_mapping import position_of


def _insert(pipeline_ctrl, main, sub1=""):
    view = pipeline_ctrl.window.latex_index_window
    view.main_entry.setText(main)
    view.sub1_entry.setText(sub1)
    pipeline_ctrl.window.latex_index_controller.handle_insert()


def _records(pipeline_ctrl):
    return pipeline_ctrl.entry_modifier_ctrl.model._records


def _find_uid(pipeline_ctrl, heading_text: str) -> int:
    for uid, rec in _records(pipeline_ctrl).items():
        if rec.heading_raw == heading_text:
            return uid
    raise AssertionError(f"no record found for heading {heading_text!r}")


def _db_row_exists(pipeline_ctrl, entry_id: int) -> bool:
    persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
    with persistence._get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM project_references WHERE unique_id_number = ?", (entry_id,)
        ).fetchone()
    return row is not None


def _saved_row_exists(pipeline_ctrl, entry_id: int) -> bool:
    """
    Whether a save would leave this entry in the database.

    Index writes are journalled and drained at save time, so asserting on
    the raw table straight after an operation says nothing useful. Saving
    first is what makes the question meaningful -- and it exercises the
    drain, which is the part that could actually be wrong.
    """
    pipeline_ctrl.execute_project_save_workflow()
    return _db_row_exists(pipeline_ctrl, entry_id)


def _undo(pipeline_ctrl, tab, qtbot):
    qtbot.keyClick(tab, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)


def _redo(pipeline_ctrl, tab, qtbot):
    qtbot.keyClick(tab, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)


# ---------------------------------------------------------------------------
# Consequence 1: an undone insertion used to leave an orphan DB row
# ---------------------------------------------------------------------------

class TestUndoingAnInsertion:
    def test_removes_the_macro_text(self, opened_project, qtbot):
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")
        before = tab.toPlainText()

        _insert(pipeline_ctrl, "BrandNew")
        assert r"\index{BrandNew}" in tab.toPlainText()

        _undo(pipeline_ctrl, tab, qtbot)

        assert tab.toPlainText() == before

    def test_removes_the_db_row_not_just_the_tree_node(self, opened_project, qtbot):
        """
        The original defect: _handle_index_undo popped the stack and called
        remove_last_entry, which touches the tree node ONLY. Insertions
        commit their DB row immediately, so undoing one left a row with no
        macro text anywhere in the project.
        """
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")

        _insert(pipeline_ctrl, "BrandNew")
        entry_id = _find_uid(pipeline_ctrl, "BrandNew")

        _undo(pipeline_ctrl, tab, qtbot)

        assert entry_id not in _records(pipeline_ctrl)
        assert _saved_row_exists(pipeline_ctrl, entry_id) is False


# ---------------------------------------------------------------------------
# Consequence 2: later entries' coordinates went stale
# ---------------------------------------------------------------------------

class TestUndoRestoresCoordinates:
    def test_a_later_entry_gets_its_coordinates_put_back(self, opened_project, qtbot):
        r"""
        Nothing called shift_coordinates_after on undo, so every entry
        after the undone macro kept coordinates describing where it used
        to be. The next rename or delete of one of those then targeted the
        wrong byte span.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        intro_uid = _find_uid(pipeline_ctrl, "Introduction")
        before_pos = position_of(_records(pipeline_ctrl)[intro_uid])

        tab = _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")
        assert position_of(_records(pipeline_ctrl)[intro_uid]) != before_pos

        _undo(pipeline_ctrl, tab, qtbot)

        assert position_of(_records(pipeline_ctrl)[intro_uid]) == before_pos

    def test_coordinates_still_describe_the_real_text(self, opened_project, qtbot):
        """The assertion that actually matters: cached position == where the macro is."""
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        intro_uid = _find_uid(pipeline_ctrl, "Introduction")

        tab = _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")
        _undo(pipeline_ctrl, tab, qtbot)

        cached = position_of(_records(pipeline_ctrl)[intro_uid])
        assert tab.toPlainText().index(r"\index{Introduction}") == cached


# ---------------------------------------------------------------------------
# Consequence 3: the sharpest one -- two operations half-reversed
# ---------------------------------------------------------------------------

class TestUndoTargetsTheLastOperation:
    def test_insert_then_delete_then_undo_reverses_only_the_delete(self, opened_project, qtbot):
        r"""
        THE defect, in one test. Insert an entry, then delete a DIFFERENT
        one, then Ctrl+Z. Qt restored the deleted macro's text while the
        index stack popped the unrelated *insertion* and removed that tree
        node -- two different operations each getting half-reversed, in a
        single keystroke.

        Undo must now reverse exactly the delete, completely, and leave
        the insertion alone.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab_at_start(pipeline_ctrl, intro_path)

        _insert(pipeline_ctrl, "BrandNew")
        inserted_id = _find_uid(pipeline_ctrl, "BrandNew")

        victim_id = _find_uid(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(victim_id)
        assert r"\index{Introduction}" not in tab.toPlainText()

        _undo(pipeline_ctrl, tab, qtbot)

        # The deletion is fully reversed: text, cache and DB row together.
        assert r"\index{Introduction}" in tab.toPlainText()
        assert victim_id in _records(pipeline_ctrl)

        # ...and the unrelated insertion is untouched.
        assert r"\index{BrandNew}" in tab.toPlainText()
        assert inserted_id in _records(pipeline_ctrl)

        # Both survive the save that actually writes them.
        pipeline_ctrl.execute_project_save_workflow()
        assert _db_row_exists(pipeline_ctrl, victim_id) is True
        assert _db_row_exists(pipeline_ctrl, inserted_id) is True

    def test_a_second_undo_then_reverses_the_insertion(self, opened_project, qtbot):
        """Undo walks back in order rather than by whatever Qt last touched."""
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab_at_start(pipeline_ctrl, intro_path)
        original = tab.toPlainText()

        _insert(pipeline_ctrl, "BrandNew")
        victim_id = _find_uid(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(victim_id)

        _undo(pipeline_ctrl, tab, qtbot)   # undoes the delete
        _undo(pipeline_ctrl, tab, qtbot)   # undoes the insert

        assert tab.toPlainText() == original


# ---------------------------------------------------------------------------
# Consequence 4: range pairs came apart
# ---------------------------------------------------------------------------

class TestRangePairsUndoAtomically:
    def _insert_range(self, pipeline_ctrl, tab, main):
        """
        A range entry is produced by inserting with a live SELECTION in
        the editor -- the opener goes before it and the closer after it.
        There is no checkbox; see test_latex_index_controller_insert.py.
        """
        cursor = tab.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
        tab.setTextCursor(cursor)
        _insert(pipeline_ctrl, main)

    def test_one_undo_removes_both_halves(self, opened_project, qtbot):
        r"""
        Only the opener was ever pushed onto the old stack, while Qt had
        recorded opener, selected text and closer as separate undo steps
        -- so one Ctrl+Z undid part of a macro pair and left the rest.
        """
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")
        before = tab.toPlainText()

        self._insert_range(pipeline_ctrl, tab, "RangeTerm")
        text_with_range = tab.toPlainText()
        assert r"\index{RangeTerm|(}" in text_with_range
        assert r"\index{RangeTerm|)}" in text_with_range

        _undo(pipeline_ctrl, tab, qtbot)

        assert tab.toPlainText() == before

    def test_both_db_rows_go(self, opened_project, qtbot):
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")

        self._insert_range(pipeline_ctrl, tab, "RangeTerm")
        pair_ids = [
            uid for uid, rec in _records(pipeline_ctrl).items()
            if rec.heading_raw.startswith("RangeTerm")
        ]
        assert len(pair_ids) == 2

        _undo(pipeline_ctrl, tab, qtbot)

        for entry_id in pair_ids:
            assert _db_row_exists(pipeline_ctrl, entry_id) is False
            assert entry_id not in _records(pipeline_ctrl)


# ---------------------------------------------------------------------------
# Redo
# ---------------------------------------------------------------------------

class TestRedo:
    def test_redo_puts_an_undone_insertion_back(self, opened_project, qtbot):
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")

        _insert(pipeline_ctrl, "BrandNew")
        after_insert = tab.toPlainText()
        _undo(pipeline_ctrl, tab, qtbot)

        _redo(pipeline_ctrl, tab, qtbot)

        assert tab.toPlainText() == after_insert

    def test_redo_restores_the_db_row_too(self, opened_project, qtbot):
        """
        The old redo called reinsert_entry, which re-added the visual tree
        node ONLY -- resurrecting a phantom entry with no backing record.
        """
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")

        _insert(pipeline_ctrl, "BrandNew")
        entry_id = _find_uid(pipeline_ctrl, "BrandNew")
        _undo(pipeline_ctrl, tab, qtbot)

        _redo(pipeline_ctrl, tab, qtbot)

        assert entry_id in _records(pipeline_ctrl)
        assert _saved_row_exists(pipeline_ctrl, entry_id) is True

    def test_undoing_a_deletion_and_redoing_it_removes_it_again(self, opened_project, qtbot):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        entry_id = _find_uid(pipeline_ctrl, "Introduction")

        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)
        _undo(pipeline_ctrl, tab, qtbot)
        assert r"\index{Introduction}" in tab.toPlainText()

        _redo(pipeline_ctrl, tab, qtbot)

        assert r"\index{Introduction}" not in tab.toPlainText()
        assert _saved_row_exists(pipeline_ctrl, entry_id) is False

    def test_a_new_action_discards_the_redo_branch(self, opened_project, qtbot):
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")

        _insert(pipeline_ctrl, "First")
        _undo(pipeline_ctrl, tab, qtbot)
        _insert(pipeline_ctrl, "Second")

        _redo(pipeline_ctrl, tab, qtbot)

        assert r"\index{First}" not in tab.toPlainText()
        assert r"\index{Second}" in tab.toPlainText()


# ---------------------------------------------------------------------------
# Table edits
# ---------------------------------------------------------------------------

class TestUndoingATableEdit:
    def test_heading_text_and_macro_both_come_back(self, opened_project, qtbot):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        entry_id = _find_uid(pipeline_ctrl, "Introduction")

        pipeline_ctrl.index_edit_ctrl.handle_entry_table_edit(entry_id, "Renamed")
        assert r"\index{Renamed}" in tab.toPlainText()

        _undo(pipeline_ctrl, tab, qtbot)

        assert r"\index{Introduction}" in tab.toPlainText()
        assert r"\index{Renamed}" not in tab.toPlainText()
        assert _records(pipeline_ctrl)[entry_id].heading_raw == "Introduction"

    def test_coordinates_survive_a_length_changing_edit(self, opened_project, qtbot):
        """A longer heading shifts everything after it; undo must shift it back."""
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        first_id = _find_uid(pipeline_ctrl, "Introduction")
        later_id = _find_uid(pipeline_ctrl, "Topics!Overview")
        before_pos = position_of(_records(pipeline_ctrl)[later_id])

        pipeline_ctrl.index_edit_ctrl.handle_entry_table_edit(
            first_id, "AMuchLongerHeadingThanBefore"
        )
        assert position_of(_records(pipeline_ctrl)[later_id]) != before_pos

        _undo(pipeline_ctrl, tab, qtbot)

        assert position_of(_records(pipeline_ctrl)[later_id]) == before_pos
        assert tab.toPlainText().index(r"\index{Topics!Overview}") == before_pos


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

class TestUndoGuard:
    def test_undo_refuses_when_the_span_no_longer_matches(self, opened_project, qtbot):
        """
        An undo whose recorded span no longer holds what it expects must
        abort rather than write over whatever is there now -- and must
        leave the command undoable so it still works once the file is
        back in a state it recognizes.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        entry_id = _find_uid(pipeline_ctrl, "Introduction")

        pipeline_ctrl.index_edit_ctrl.handle_entry_table_edit(entry_id, "Renamed")
        assert pipeline_ctrl._index_commands.can_undo is True

        # Something else rewrites the span out from under the command.
        location = pipeline_ctrl.entry_modifier_model.get_location_metadata(entry_id)
        pipeline_ctrl.doc_io.rewrite_macro_span(
            str(intro_path),
            location["absolute_position"],
            location["absolute_end"],
            r"\index{SomethingElse}",
        )

        _undo(pipeline_ctrl, tab, qtbot)

        assert r"\index{SomethingElse}" in tab.toPlainText()   # not clobbered
        assert pipeline_ctrl._index_commands.can_undo is True  # still undoable

    def test_stack_is_cleared_on_project_load(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        _open_tab_at_start(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")
        _insert(pipeline_ctrl, "BrandNew")
        assert pipeline_ctrl._index_commands.can_undo is True

        pipeline_ctrl._resync_index_data_from_disk()

        assert pipeline_ctrl._index_commands.can_undo is False
