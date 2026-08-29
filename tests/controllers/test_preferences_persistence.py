"""
PreferencesPersistence -- global (QSettings-backed) application
preferences: window layout, font, dark mode, last-project tracking, and
the global (non-project-scoped) copy of index/formatting prefs. Real,
non-trivial logic that had zero coverage anywhere before this file: two
one-time migrations that run on every construction (a legacy QSettings
org/app location, and a legacy ist_*->fmt_* key rename within
IndexPrefs/global), plus load_application_preferences's type coercion
(font_size to int, dark_mode to bool, geometry/state/splitter_state
hex-encoded QByteArray round-tripping, *path key normalization).

QSettings is process-global -- redirected to a per-test tmp_path via
IniFormat, same pattern as the other QSettings-touching test files. Both
the bare QSettings() location AND the explicit legacy
QSettings("DH Indexing", "LatexEditor") location land under the same
redirected tmp_path, so migration between them is still test-isolated.
"""
import json

import pytest
from PySide6.QtCore import QSettings, QByteArray

from models.preferences_persistence import PreferencesPersistence


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


class TestLegacySettingsLocationMigration:
    def test_migrates_a_key_from_the_legacy_location(self, qtbot):
        legacy = QSettings("DH Indexing", "LatexEditor")
        legacy.setValue("font_family", "Consolas")
        legacy.sync()

        prefs = PreferencesPersistence()

        assert prefs.settings.value("font_family") == "Consolas"

    def test_clears_the_legacy_location_after_migrating(self, qtbot):
        legacy = QSettings("DH Indexing", "LatexEditor")
        legacy.setValue("font_family", "Consolas")
        legacy.sync()

        PreferencesPersistence()

        legacy_after = QSettings("DH Indexing", "LatexEditor")
        assert legacy_after.allKeys() == []

    def test_does_not_overwrite_an_already_present_new_location_value(self, qtbot):
        legacy = QSettings("DH Indexing", "LatexEditor")
        legacy.setValue("font_family", "LegacyFont")
        legacy.sync()
        current = QSettings()
        current.setValue("font_family", "AlreadyThere")
        current.sync()

        prefs = PreferencesPersistence()

        assert prefs.settings.value("font_family") == "AlreadyThere"

    def test_no_legacy_data_is_a_noop(self, qtbot):
        prefs = PreferencesPersistence()  # must not raise
        assert prefs.settings.value("font_family", "Arial") == "Arial"


class TestLegacyIndexPrefsKeyMigration:
    def test_renames_a_legacy_ist_key_to_fmt(self, qtbot):
        settings = QSettings()
        settings.beginGroup("IndexPrefs/global")
        settings.setValue("ist_page_delimiter", "; ")
        settings.endGroup()
        settings.sync()

        prefs = PreferencesPersistence()

        prefs.settings.beginGroup("IndexPrefs/global")
        try:
            assert prefs.settings.value("fmt_page_delimiter") == "; "
            assert not prefs.settings.contains("ist_page_delimiter")
        finally:
            prefs.settings.endGroup()

    def test_does_not_clobber_an_existing_fmt_value(self, qtbot):
        settings = QSettings()
        settings.beginGroup("IndexPrefs/global")
        settings.setValue("ist_page_delimiter", "LEGACY")
        settings.setValue("fmt_page_delimiter", "CURRENT")
        settings.endGroup()
        settings.sync()

        prefs = PreferencesPersistence()

        prefs.settings.beginGroup("IndexPrefs/global")
        try:
            assert prefs.settings.value("fmt_page_delimiter") == "CURRENT"
        finally:
            prefs.settings.endGroup()


class TestLoadApplicationPreferences:
    def test_defaults_when_nothing_is_stored(self, qtbot):
        prefs = PreferencesPersistence()

        loaded = prefs.load_application_preferences()

        assert loaded["font_family"] == "Arial"
        assert loaded["font_size"] == 12
        assert loaded["dark_mode"] is False

    def test_font_size_is_coerced_to_int(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("font_size", "16")

        loaded = prefs.load_application_preferences()

        assert loaded["font_size"] == 16
        assert isinstance(loaded["font_size"], int)

    def test_invalid_font_size_falls_back_to_the_default(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("font_size", "not-a-number")

        loaded = prefs.load_application_preferences()

        assert loaded["font_size"] == 12

    def test_dark_mode_string_true_coerces_to_bool_true(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("dark_mode", "true")

        assert prefs.load_application_preferences()["dark_mode"] is True

    def test_dark_mode_string_false_coerces_to_bool_false(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("dark_mode", "false")

        assert prefs.load_application_preferences()["dark_mode"] is False


class TestLayoutStateRoundTrip:
    """
    The hex round trip itself moved to `bookindexcore.ui.window` at step 11f,
    where it is tested against a window and a splitter rather than against a
    blob. What stays here is the part that is this application's own: an
    existing layout, stored under this application's key names since long
    before the shared helper existed, has to survive the change.
    """

    def test_geometry_round_trips_through_hex_encoding(self, qtbot):
        prefs = PreferencesPersistence()
        original = QByteArray(b"some binary geometry data")

        prefs.serialize_layout_state({"geometry": original})
        loaded = prefs.load_application_preferences()

        assert isinstance(loaded["geometry"], QByteArray)
        assert bytes(loaded["geometry"].data()) == b"some binary geometry data"

    def test_state_round_trips_through_hex_encoding(self, qtbot):
        prefs = PreferencesPersistence()
        original = QByteArray(b"some window state blob")

        prefs.serialize_layout_state({"state": original})
        loaded = prefs.load_application_preferences()

        assert bytes(loaded["state"].data()) == b"some window state blob"

    def test_an_existing_layout_moves_to_the_shared_keys(self, qtbot):
        """
        Without this an indexer's own division of the screen is thrown away
        once, on the first launch after the change, and nothing says why.
        """
        prefs = PreferencesPersistence()
        prefs.settings.setValue("window_geometry", "abcd")
        prefs.settings.setValue("splitter_state", "ef01")
        prefs.settings.remove("layout/geometry")

        prefs.migrate_layout_state()

        assert prefs.settings.value("layout/geometry") == "abcd"
        assert prefs.settings.value("layout/splitter/main") == "ef01"
        assert prefs.settings.value("window_geometry") is None

    def test_it_does_not_overwrite_a_layout_already_moved(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("layout/geometry", "beef")
        prefs.settings.setValue("window_geometry", "abcd")

        prefs.migrate_layout_state()

        assert prefs.settings.value("layout/geometry") == "beef"


class TestProjectContextAndVisualPreferences:
    def test_update_project_context_persists_root_and_name(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.update_project_context("/some/path", "MyProject")

        loaded = prefs.load_application_preferences()
        assert loaded["last_project_name"] == "MyProject"

    def test_update_visual_preferences_persists_font_and_dark_mode(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.update_visual_preferences("Consolas", 14, True)

        loaded = prefs.load_application_preferences()
        assert loaded["font_family"] == "Consolas"
        assert loaded["font_size"] == 14
        assert loaded["dark_mode"] is True

    def test_get_last_project_path_normalizes_the_path(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.update_fallback_directory("/some/../normalized/path")

        result = prefs.get_last_project_path()

        assert ".." not in result


class TestIndexPrefsRoundTrip:
    def test_save_and_load_round_trips_values(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.save_index_prefs({"fmt_page_delimiter": "; ", "imakeidx_columns": 3, "use_imakeidx": False})

        loaded = prefs.load_index_prefs()
        assert loaded["fmt_page_delimiter"] == "; "
        assert loaded["imakeidx_columns"] == 3
        assert loaded["use_imakeidx"] is False

    def test_load_with_nothing_saved_returns_dataclass_defaults(self, qtbot):
        prefs = PreferencesPersistence()

        loaded = prefs.load_index_prefs()

        assert loaded["index_engine"] == "makeindex"
        assert loaded["use_imakeidx"] is True


class TestGeneralPreferences:
    """
    Preferences -> General: undo depth, auto-save, log folder name, and the
    bold/italic encap lists. Application-scoped, so unlike the LaTeX
    settings these live in QSettings only and never reach project_metadata.

    The coercion matters more here than it looks: QSettings hands values
    back as strings from an .ini and as native types from the Windows
    registry, and every one of these feeds something that would fail far
    from the cause if it arrived as the wrong type -- a QTimer interval, a
    stack bound, a frozenset membership test.
    """

    def test_defaults_when_nothing_is_stored(self, qtbot):
        prefs = PreferencesPersistence()

        data = prefs.load_application_preferences()

        assert data["undo_stack_size"] == 200
        assert data["autosave_enabled"] is True
        assert data["autosave_interval_minutes"] == 5
        assert data["log_directory_name"] == "session_logs"
        assert data["encap_bold_values"] == ["bold", "textbf", "bf"]
        assert data["encap_italic_values"] == ["textit", "it", "italic"]

    def test_log_folder_default_is_visible_not_hidden(self, qtbot):
        """
        The default changed from '.session_logs' to 'session_logs' on
        purpose -- a folder the user is meant to open and read should not
        be hidden, on any platform (a leading dot hides it on macOS and
        Linux; the app also used to set the Windows hidden attribute).
        """
        prefs = PreferencesPersistence()

        assert not prefs.load_application_preferences()["log_directory_name"].startswith(".")

    def test_round_trips_every_general_value(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.update_general_preferences({
            "undo_stack_size": 50,
            "autosave_enabled": False,
            "autosave_interval_minutes": 15,
            "log_directory_name": "logs",
            "encap_bold_values": ["strong", "textbf"],
            "encap_italic_values": ["emph"],
        })

        data = prefs.load_application_preferences()
        assert data["undo_stack_size"] == 50
        assert data["autosave_enabled"] is False
        assert data["autosave_interval_minutes"] == 15
        assert data["log_directory_name"] == "logs"
        assert data["encap_bold_values"] == ["strong", "textbf"]
        assert data["encap_italic_values"] == ["emph"]

    def test_a_single_item_list_survives_the_round_trip(self, qtbot):
        """
        The case that breaks a naive implementation: QSettings stores a
        one-item list and hands back a bare string, which then splits into
        individual characters if it is treated as a sequence.
        """
        prefs = PreferencesPersistence()

        prefs.update_general_preferences({"encap_italic_values": ["emph"]})

        assert prefs.load_application_preferences()["encap_italic_values"] == ["emph"]

    def test_string_valued_int_is_coerced(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("autosave_interval_minutes", "20")

        assert prefs.load_application_preferences()["autosave_interval_minutes"] == 20

    def test_malformed_int_falls_back_to_the_default(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("undo_stack_size", "not-a-number")

        assert prefs.load_application_preferences()["undo_stack_size"] == 200

    def test_zero_interval_is_clamped(self, qtbot):
        """A zero here would be a QTimer firing continuously."""
        prefs = PreferencesPersistence()
        prefs.settings.setValue("autosave_interval_minutes", 0)

        assert prefs.load_application_preferences()["autosave_interval_minutes"] == 1

    def test_zero_undo_depth_is_clamped(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("undo_stack_size", 0)

        assert prefs.load_application_preferences()["undo_stack_size"] == 1

    def test_blank_log_folder_falls_back_to_the_default(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("log_directory_name", "   ")

        assert prefs.load_application_preferences()["log_directory_name"] == "session_logs"

    def test_autosave_enabled_accepts_a_string_boolean(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("autosave_enabled", "false")

        assert prefs.load_application_preferences()["autosave_enabled"] is False


class TestRecentProjectsSettings:
    """The two Preferences -> General settings that govern the list. The list
    itself is covered by TestRecentProjectsList."""

    def test_defaults(self, qtbot):
        data = PreferencesPersistence().load_application_preferences()

        assert data["recent_projects_enabled"] is True
        assert data["recent_projects_max"] == 10

    def test_enabled_accepts_a_string_boolean(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("recent_projects_enabled", "false")

        assert prefs.load_application_preferences()["recent_projects_enabled"] is False

    def test_count_round_trips_through_update_general_preferences(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.update_general_preferences(
            {"recent_projects_enabled": False, "recent_projects_max": 3}
        )

        data = PreferencesPersistence().load_application_preferences()
        assert data["recent_projects_max"] == 3
        assert data["recent_projects_enabled"] is False

    def test_count_is_clamped_to_the_spin_box_range_on_write(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.update_general_preferences({"recent_projects_max": 999})
        assert prefs.load_application_preferences()["recent_projects_max"] == 25

        prefs.update_general_preferences({"recent_projects_max": 0})
        assert prefs.load_application_preferences()["recent_projects_max"] == 1

    def test_a_hand_edited_out_of_range_count_is_clamped_on_read(self, qtbot):
        # A value that never went through the dialog -- a stale registry key
        # or a hand-edited .ini.
        prefs = PreferencesPersistence()
        prefs.settings.setValue("recent_projects_max", 500)

        assert prefs.load_application_preferences()["recent_projects_max"] == 25

    def test_the_raw_list_does_not_leak_into_the_preferences_dict(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.record_recent_project(r"D:\Books\Smith", "Smith")

        data = prefs.load_application_preferences()

        assert "recent_projects" not in data, (
            "the JSON blob has its own accessor and must not appear as a raw "
            "string beside the typed preferences")


class TestRecentProjectsList:
    """
    Stored as JSON rather than the comma-joined form the other list
    preferences use, because a comma is legal in a filesystem path.
    """

    def test_empty_by_default(self, qtbot):
        assert PreferencesPersistence().get_recent_projects() == []

    def test_most_recently_opened_comes_first(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.record_recent_project(r"D:\Books\First", "First")
        prefs.record_recent_project(r"D:\Books\Second", "Second")

        assert [e["name"] for e in prefs.get_recent_projects()] == ["Second", "First"]

    def test_reopening_moves_an_entry_up_rather_than_duplicating_it(self, qtbot):
        prefs = PreferencesPersistence()

        prefs.record_recent_project(r"D:\Books\First", "First")
        prefs.record_recent_project(r"D:\Books\Second", "Second")
        prefs.record_recent_project(r"D:\Books\First", "First")

        entries = prefs.get_recent_projects()
        assert [e["name"] for e in entries] == ["First", "Second"]
        assert len(entries) == 2

    def test_paths_differing_only_in_case_are_the_same_project(self, qtbot):
        # Windows paths are case-insensitive, so these are one project.
        prefs = PreferencesPersistence()

        prefs.record_recent_project(r"D:\Books\Smith", "Smith")
        prefs.record_recent_project(r"d:\books\smith", "Smith")

        assert len(prefs.get_recent_projects()) == 1

    def test_a_path_containing_a_comma_survives(self, qtbot):
        # The reason this list is JSON and not comma-joined like the others.
        prefs = PreferencesPersistence()
        path = r"D:\Books\Smith, John - Torts"

        prefs.record_recent_project(path, "Torts")

        assert prefs.get_recent_projects()[0]["path"] == path

    def test_storage_is_capped(self, qtbot):
        prefs = PreferencesPersistence()

        for i in range(40):
            prefs.record_recent_project(rf"D:\Books\P{i}", f"P{i}")

        entries = prefs.get_recent_projects()
        assert len(entries) == 25
        assert entries[0]["name"] == "P39", "the newest must survive the cap"

    def test_forget_removes_one_entry_only(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.record_recent_project(r"D:\Books\First", "First")
        prefs.record_recent_project(r"D:\Books\Second", "Second")

        prefs.forget_recent_project(r"D:\Books\First")

        assert [e["name"] for e in prefs.get_recent_projects()] == ["Second"]

    def test_forget_matches_case_insensitively(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.record_recent_project(r"D:\Books\Smith", "Smith")

        prefs.forget_recent_project(r"d:\books\SMITH")

        assert prefs.get_recent_projects() == []

    def test_clear_empties_the_list(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.record_recent_project(r"D:\Books\First", "First")

        prefs.clear_recent_projects()

        assert prefs.get_recent_projects() == []

    def test_a_corrupt_stored_value_is_survived(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("recent_projects", "{not json")

        assert prefs.get_recent_projects() == []
        # And the next open repairs it rather than raising.
        prefs.record_recent_project(r"D:\Books\First", "First")
        assert [e["name"] for e in prefs.get_recent_projects()] == ["First"]

    def test_an_entry_without_a_path_is_dropped(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("recent_projects", json.dumps([
            {"path": "", "name": "ghost"},
            {"path": r"D:\Books\Real", "name": "Real"},
        ]))

        assert [e["name"] for e in prefs.get_recent_projects()] == ["Real"]

    def test_a_non_list_stored_value_is_survived(self, qtbot):
        prefs = PreferencesPersistence()
        prefs.settings.setValue("recent_projects", json.dumps({"path": "D:/x"}))

        assert prefs.get_recent_projects() == []
