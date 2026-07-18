"""
IndexPrefsConfigModel -- pure logic (dataclasses only, no PySide6) driving
the LaTeX Settings preferences dialog: coercion/legacy-key migration on
update_data, the .ist/.xdy style-file generators, and the
preamble/printindex snippet builders injected into the project's base
file. The persistence-touching methods (seed_project_from_globals,
load_from_project, persist_to_project) use the real FileTreePersistence
via the fresh_persistence fixture -- cheap, real sqlite, no reason to fake
it.

Exact generated-string assertions below were captured from the actual
running code rather than guessed, since the .ist/.xdy formats have
specific escaping (double-backslash literals for LaTeX/xindy escape
sequences) that's easy to get subtly wrong by inspection alone.
"""
from models.index_prefs_config_model import IndexPrefsConfigModel, LEGACY_INDEX_PREFS_KEY_ALIASES


class TestUpdateData:
    def test_bool_field_coerces_from_string_true(self):
        model = IndexPrefsConfigModel()
        model.update_data({"use_imakeidx": "true"})
        assert model._data.use_imakeidx is True

    def test_bool_field_coerces_from_string_false(self):
        model = IndexPrefsConfigModel()
        model.update_data({"use_imakeidx": "false"})
        assert model._data.use_imakeidx is False

    def test_int_field_coerces_from_string(self):
        model = IndexPrefsConfigModel()
        model.update_data({"imakeidx_columns": "5"})
        assert model._data.imakeidx_columns == 5
        assert isinstance(model._data.imakeidx_columns, int)

    def test_invalid_int_falls_back_to_the_default(self):
        model = IndexPrefsConfigModel()
        model.update_data({"imakeidx_columns": "not-an-int"})
        assert model._data.imakeidx_columns == 2  # dataclass default

    def test_unknown_key_is_silently_ignored(self):
        model = IndexPrefsConfigModel()
        model.update_data({"totally_unknown_key": "whatever"})  # must not raise
        assert not hasattr(model._data, "totally_unknown_key")

    def test_str_field_is_stringified(self):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_symbols_label": "Syms"})
        assert model._data.fmt_symbols_label == "Syms"

    def test_legacy_ist_key_is_mapped_to_its_fmt_replacement(self):
        model = IndexPrefsConfigModel()
        model.update_data({"ist_page_delimiter": "; "})
        assert model._data.fmt_page_delimiter == "; "

    def test_every_declared_legacy_alias_maps_to_a_real_field(self):
        model = IndexPrefsConfigModel()
        defaults = model.serialize_to_dict()
        for new_key in LEGACY_INDEX_PREFS_KEY_ALIASES.values():
            assert new_key in defaults


class TestSerializeAndLoad:
    def test_load_from_dict_round_trips_through_serialize_to_dict(self):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_symbols_label": "Custom"})
        payload = model.serialize_to_dict()

        restored = IndexPrefsConfigModel()
        restored.load_from_dict(payload)

        assert restored.serialize_to_dict() == payload


class TestGenerateIstContent:
    def test_default_content(self):
        model = IndexPrefsConfigModel()
        content = model.generate_ist_content()
        assert 'headings_flag 1' in content
        assert r'heading_prefix "\\n\\textbf{"' in content
        assert 'symhead_positive "Symbols"' in content
        assert 'numhead_positive "Numbers"' in content
        assert 'delim_0 ", "' in content
        assert 'delim_r "--"' in content

    def test_headings_disabled_omits_prefix_suffix_lines(self):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_enable_headings": False})
        content = model.generate_ist_content()
        assert "headings_flag 0" in content
        assert "heading_prefix" not in content

    def test_headings_not_bold_uses_the_non_bold_prefix(self):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_heading_bold": False})
        content = model.generate_ist_content()
        assert r'heading_prefix "\\n{"' in content

    def test_dot_leaders_use_dotfill_instead_of_the_page_delimiter(self):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_use_dot_leaders": True})
        content = model.generate_ist_content()
        assert r'delim_0 "\\dotfill"' in content
        assert r'delim_1 "\\dotfill"' in content
        assert r'delim_2 "\\dotfill"' in content
        # delim_n always uses the literal page delimiter, dot leaders or not.
        assert 'delim_n ", "' in content


class TestGenerateXdyContent:
    def test_default_content(self):
        model = IndexPrefsConfigModel()
        content = model.generate_xdy_content()
        assert '(require "english")' in content
        assert '(require "utf8.xdy")' in content
        assert '(markup-letter-group-list :open "\\n" :close "\\nopagebreak\\n" :open-head "\\textbf{" :close-head "}")' in content
        assert '(markup-index :allow-duplicate-page-refs true)' in content

    def test_headings_disabled_uses_empty_open_close(self):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_enable_headings": False})
        content = model.generate_xdy_content()
        assert '(markup-letter-group-list :open "" :close "")' in content

    def test_duplicates_disallowed_omits_the_markup_index_line(self):
        model = IndexPrefsConfigModel()
        model.update_data({"xindy_allow_duplicates": False})
        content = model.generate_xdy_content()
        assert "markup-index" not in content

    def test_custom_language_and_codepage_are_used(self):
        model = IndexPrefsConfigModel()
        model.update_data({"xindy_language": "german", "xindy_codepage": "latin1"})
        content = model.generate_xdy_content()
        assert '(require "german")' in content
        assert '(require "latin1.xdy")' in content


class TestEngineDispatch:
    def test_generate_index_style_content_dispatches_to_ist_by_default(self):
        model = IndexPrefsConfigModel()
        assert model.generate_index_style_content() == model.generate_ist_content()

    def test_generate_index_style_content_dispatches_to_xdy_for_xindy(self):
        model = IndexPrefsConfigModel()
        model.update_data({"index_engine": "xindy"})
        assert model.generate_index_style_content() == model.generate_xdy_content()

    def test_get_index_style_filename_makeindex(self):
        model = IndexPrefsConfigModel()
        assert model.get_index_style_filename() == "default.ist"

    def test_get_index_style_filename_xindy(self):
        model = IndexPrefsConfigModel()
        model.update_data({"index_engine": "xindy"})
        assert model.get_index_style_filename() == "default.xdy"

    def test_get_command_binary_matches_the_engine_name(self):
        model = IndexPrefsConfigModel()
        assert model.get_command_binary() == "makeindex"
        model.update_data({"index_engine": "xindy"})
        assert model.get_command_binary() == "xindy"


class TestGetPrintindexCommandName:
    def test_default(self):
        assert IndexPrefsConfigModel().get_printindex_command_name() == "printindex"

    def test_strips_leading_backslash(self):
        model = IndexPrefsConfigModel()
        model.update_data({"printindex_command": r"\myindex"})
        assert model.get_printindex_command_name() == "myindex"

    def test_empty_falls_back_to_printindex(self):
        model = IndexPrefsConfigModel()
        model.update_data({"printindex_command": ""})
        assert model.get_printindex_command_name() == "printindex"


class TestGeneratePreambleSnippet:
    def test_default_includes_imakeidx_and_idxlayout_only(self):
        model = IndexPrefsConfigModel()
        snippet = model.generate_preamble_snippet()
        assert r"\usepackage[noautomatic,nonewpage]{imakeidx}" in snippet
        assert r"\makeindex[columns=2, options={-c -s default.ist}]" in snippet
        assert r"\usepackage[unbalanced=true]{idxlayout}" in snippet
        assert "hyperref" not in snippet

    def test_everything_disabled_returns_empty_string(self):
        model = IndexPrefsConfigModel()
        model.update_data({"use_imakeidx": False, "use_idxlayout": False})
        assert model.generate_preamble_snippet() == ""

    def test_xindy_engine_adds_xindy_option_and_cli_flags(self):
        model = IndexPrefsConfigModel()
        model.update_data({"index_engine": "xindy", "xindy_language": "german", "xindy_codepage": "latin1"})
        snippet = model.generate_preamble_snippet()
        assert "xindy" in snippet
        assert "-L german -C latin1" in snippet

    def test_hyperref_with_colorlinks_and_custom_color(self):
        model = IndexPrefsConfigModel()
        model.update_data({
            "include_hyperref": True, "hyperref_colorlinks": True, "hyperref_linkcolor": "red",
        })
        snippet = model.generate_preamble_snippet()
        assert r"\usepackage[colorlinks,linkcolor=red]{hyperref}" in snippet

    def test_multicols_package_included_when_enabled(self):
        model = IndexPrefsConfigModel()
        model.update_data({"printindex_use_multicols": True})
        assert r"\usepackage{multicol}" in model.generate_preamble_snippet()


class TestGeneratePrintindexSnippet:
    def test_default_is_a_bare_command(self):
        assert IndexPrefsConfigModel().generate_printindex_snippet() == r"\printindex"

    def test_custom_command_name(self):
        model = IndexPrefsConfigModel()
        model.update_data({"printindex_command": "myindex"})
        assert model.generate_printindex_snippet() == r"\myindex"

    def test_multicols_wraps_the_command_using_imakeidx_columns(self):
        model = IndexPrefsConfigModel()
        model.update_data({"printindex_use_multicols": True, "imakeidx_columns": 3})
        assert model.generate_printindex_snippet() == "\\begin{multicols}{3}\n\\printindex\n\\end{multicols}"

    def test_multicols_defaults_to_two_columns_when_imakeidx_disabled(self):
        model = IndexPrefsConfigModel()
        model.update_data({"printindex_use_multicols": True, "use_imakeidx": False})
        assert "{2}" in model.generate_printindex_snippet()


class TestProjectPersistence:
    def test_persist_to_project_writes_prefixed_and_structural_keys(self, fresh_persistence):
        model = IndexPrefsConfigModel()
        model.update_data({"fmt_page_delimiter": "; ", "pdflatex_path": "/usr/bin/pdflatex"})

        model.persist_to_project(fresh_persistence)

        meta = fresh_persistence.get_all_project_metadata()
        assert meta["pref_fmt_page_delimiter"] == "; "
        assert meta["compiler_executable"] == "/usr/bin/pdflatex"
        assert "pref_pdflatex_path" not in meta  # structural, not prefixed

    def test_load_from_project_round_trips_persisted_values(self, fresh_persistence):
        original = IndexPrefsConfigModel()
        original.update_data({"fmt_page_delimiter": "; ", "pdflatex_path": "/usr/bin/pdflatex"})
        original.persist_to_project(fresh_persistence)

        loaded = IndexPrefsConfigModel()
        loaded.load_from_project(fresh_persistence)

        assert loaded._data.fmt_page_delimiter == "; "
        assert loaded._data.pdflatex_path == "/usr/bin/pdflatex"

    def test_seed_project_from_globals_only_fills_missing_keys(self, fresh_persistence):
        model = IndexPrefsConfigModel()
        model.seed_project_from_globals({"fmt_page_delimiter": "; "}, fresh_persistence)
        assert fresh_persistence.get_all_project_metadata()["pref_fmt_page_delimiter"] == "; "

        # A second seed with a different value must NOT clobber what's already there.
        model.seed_project_from_globals({"fmt_page_delimiter": "CHANGED"}, fresh_persistence)
        assert fresh_persistence.get_all_project_metadata()["pref_fmt_page_delimiter"] == "; "

    def test_seed_project_from_globals_seeds_structural_columns_only_while_blank(self, fresh_persistence):
        model = IndexPrefsConfigModel()
        model.seed_project_from_globals({"pdflatex_path": "/usr/bin/pdflatex"}, fresh_persistence)
        assert fresh_persistence.get_all_project_metadata()["compiler_executable"] == "/usr/bin/pdflatex"

        model.seed_project_from_globals({"pdflatex_path": "/somewhere/else"}, fresh_persistence)
        assert fresh_persistence.get_all_project_metadata()["compiler_executable"] == "/usr/bin/pdflatex"

    def test_load_from_project_migrates_a_fresh_legacy_key(self, fresh_persistence):
        fresh_persistence.set_metadata_value("pref_ist_page_delimiter", "LEGACYVAL")

        model = IndexPrefsConfigModel()
        model.load_from_project(fresh_persistence)

        assert model._data.fmt_page_delimiter == "LEGACYVAL"
        meta = fresh_persistence.get_all_project_metadata()
        assert "pref_ist_page_delimiter" not in meta
        assert meta["pref_fmt_page_delimiter"] == "LEGACYVAL"

    def test_load_from_project_migration_does_not_clobber_an_existing_new_key(self, fresh_persistence):
        fresh_persistence.set_metadata_value("pref_fmt_page_delimiter", "; ")
        fresh_persistence.set_metadata_value("pref_ist_page_delimiter", "LEGACYVAL")

        model = IndexPrefsConfigModel()
        model.load_from_project(fresh_persistence)

        assert model._data.fmt_page_delimiter == "; "
        assert "pref_ist_page_delimiter" not in fresh_persistence.get_all_project_metadata()
