"""
ThemeConfigModel -- pure logic (dataclasses only, no PySide6) backing the
theme/preferences dialog's dark/light colour sets. Mirrors
IndexPrefsConfigModel's seed/load/persist pattern (see
test_index_prefs_config_model.py) but was never itself tested.
"""
from dataclasses import asdict

from models.theme_config_model import ThemeConfigModel, DarkThemeColours, LightThemeColours


class TestDefaults:
    def test_dark_and_light_defaults_are_distinct(self):
        model = ThemeConfigModel()
        assert model.get_dark().window != model.get_light().window

    def test_serialize_dark_matches_the_dataclass_defaults(self):
        model = ThemeConfigModel()
        assert model.serialize_dark() == asdict(DarkThemeColours())

    def test_serialize_light_matches_the_dataclass_defaults(self):
        model = ThemeConfigModel()
        assert model.serialize_light() == asdict(LightThemeColours())


class TestUpdate:
    def test_update_dark_applies_a_valid_key(self):
        model = ThemeConfigModel()
        model.update_dark({"window": "#123456"})
        assert model.get_dark().window == "#123456"

    def test_update_light_applies_a_valid_key(self):
        model = ThemeConfigModel()
        model.update_light({"text": "#abcdef"})
        assert model.get_light().text == "#abcdef"

    def test_unknown_key_is_silently_ignored(self):
        model = ThemeConfigModel()
        model.update_dark({"totally_unknown_field": "#000000"})  # must not raise
        assert not hasattr(model.get_dark(), "totally_unknown_field")

    def test_non_string_value_is_silently_ignored(self):
        model = ThemeConfigModel()
        original = model.get_dark().window
        model.update_dark({"window": 12345})
        assert model.get_dark().window == original

    def test_update_dark_does_not_touch_light(self):
        model = ThemeConfigModel()
        original_light_window = model.get_light().window
        model.update_dark({"window": "#123456"})
        assert model.get_light().window == original_light_window


class TestPrefixedSerialization:
    def test_dark_keys_get_the_dark_prefix(self):
        model = ThemeConfigModel()
        prefixed = model.serialize_dark_prefixed()
        assert all(k.startswith("theme_dark_") for k in prefixed)
        assert prefixed["theme_dark_window"] == model.get_dark().window

    def test_light_keys_get_the_light_prefix(self):
        model = ThemeConfigModel()
        prefixed = model.serialize_light_prefixed()
        assert all(k.startswith("theme_light_") for k in prefixed)

    def test_load_from_dict_updates_both_sets(self):
        model = ThemeConfigModel()
        model.load_from_dict({"window": "#111111"}, {"window": "#222222"})
        assert model.get_dark().window == "#111111"
        assert model.get_light().window == "#222222"


class TestProjectPersistence:
    def test_persist_to_project_writes_prefixed_keys(self, fresh_persistence):
        model = ThemeConfigModel()
        model.update_dark({"window": "#111111"})

        model.persist_to_project(fresh_persistence)

        meta = fresh_persistence.get_all_project_metadata()
        assert meta["theme_dark_window"] == "#111111"

    def test_load_from_project_round_trips_persisted_values(self, fresh_persistence):
        original = ThemeConfigModel()
        original.update_dark({"window": "#111111"})
        original.update_light({"text": "#222222"})
        original.persist_to_project(fresh_persistence)

        loaded = ThemeConfigModel()
        loaded.load_from_project(fresh_persistence)

        assert loaded.get_dark().window == "#111111"
        assert loaded.get_light().text == "#222222"

    def test_seed_project_from_globals_only_fills_missing_keys(self, fresh_persistence):
        model = ThemeConfigModel()
        model.seed_project_from_globals({"window": "#111111"}, {"window": "#222222"}, fresh_persistence)
        assert fresh_persistence.get_all_project_metadata()["theme_dark_window"] == "#111111"

        model.seed_project_from_globals({"window": "#CHANGED"}, {"window": "#CHANGED"}, fresh_persistence)

        assert fresh_persistence.get_all_project_metadata()["theme_dark_window"] == "#111111"
