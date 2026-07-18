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
