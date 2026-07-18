"""
LatexCommandRegistryModel -- the global (cross-project) custom-LaTeX-
command registry, backed by real QSettings. Not layer-1 pure logic (it
has a PySide6.QtCore.QSettings dependency), so it lives here rather than
tests/unit/models/, alongside the other QSettings-touching gotchas this
suite already isolates carefully.

QSettings is process-global state (Windows registry, or an .ini file
under IniFormat) -- an autouse fixture redirects it to a per-test
tmp_path via IniFormat before every test in this file, the same
redirection tests/conftest.py's booted_app fixture does for the whole
app. Without this, running these tests would read/write the real
developer machine's registry.
"""
import pytest
from PySide6.QtCore import QSettings

from models.latex_command_registry_model import LatexCommandRegistryModel


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


class TestSaveAndList:
    def test_save_then_list_returns_the_command(self):
        registry = LatexCommandRegistryModel()

        registry.save_command(r"\myindex", r"\newcommand{\myindex}[1]{\index{#1}}")

        assert registry.list_commands() == [
            {"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"}
        ]

    def test_no_commands_returns_empty_list(self):
        assert LatexCommandRegistryModel().list_commands() == []

    def test_saving_the_same_name_twice_overwrites_the_body(self):
        registry = LatexCommandRegistryModel()
        registry.save_command(r"\myindex", "first body")
        registry.save_command(r"\myindex", "second body")

        commands = registry.list_commands()
        assert len(commands) == 1
        assert commands[0]["body"] == "second body"

    def test_persists_across_separate_instances(self):
        """QSettings-backed, so a second, independently-constructed model must see it."""
        LatexCommandRegistryModel().save_command(r"\myindex", "body")

        assert LatexCommandRegistryModel().list_commands() == [
            {"name": r"\myindex", "body": "body"}
        ]


class TestCommandExists:
    def test_true_for_a_saved_command(self):
        registry = LatexCommandRegistryModel()
        registry.save_command(r"\myindex", "body")
        assert registry.command_exists(r"\myindex") is True

    def test_false_for_an_unsaved_command(self):
        assert LatexCommandRegistryModel().command_exists(r"\nope") is False


class TestRemoveCommand:
    def test_removes_a_saved_command(self):
        registry = LatexCommandRegistryModel()
        registry.save_command(r"\myindex", "body")

        registry.remove_command(r"\myindex")

        assert registry.list_commands() == []

    def test_removing_an_unknown_command_does_not_raise(self):
        registry = LatexCommandRegistryModel()
        registry.remove_command(r"\nope")  # must not raise
        assert registry.list_commands() == []

    def test_only_removes_the_named_command(self):
        registry = LatexCommandRegistryModel()
        registry.save_command(r"\a", "a-body")
        registry.save_command(r"\b", "b-body")

        registry.remove_command(r"\a")

        assert registry.list_commands() == [{"name": r"\b", "body": "b-body"}]


class TestClearCommands:
    def test_removes_every_saved_command(self):
        registry = LatexCommandRegistryModel()
        registry.save_command(r"\a", "a-body")
        registry.save_command(r"\b", "b-body")

        registry.clear_commands()

        assert registry.list_commands() == []

    def test_is_safe_to_call_with_nothing_saved(self):
        LatexCommandRegistryModel().clear_commands()  # must not raise


class TestFilterIndexingNewcommands:
    def test_keeps_a_newcommand_that_calls_index(self):
        commands = [{"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"}]
        assert LatexCommandRegistryModel.filter_indexing_newcommands(commands) == commands

    def test_keeps_renewcommand_and_providecommand_variants(self):
        commands = [
            {"name": r"\a", "body": r"\renewcommand{\a}[1]{\index{#1}}"},
            {"name": r"\b", "body": r"\providecommand{\b}[1]{\index{#1}}"},
        ]
        assert LatexCommandRegistryModel.filter_indexing_newcommands(commands) == commands

    def test_keeps_a_starred_newcommand(self):
        commands = [{"name": r"\a", "body": r"\newcommand*{\a}[1]{\index{#1}}"}]
        assert LatexCommandRegistryModel.filter_indexing_newcommands(commands) == commands

    def test_keeps_a_bracket_style_index_call(self):
        commands = [{"name": r"\a", "body": r"\newcommand{\a}[1]{\index[symbols]{#1}}"}]
        assert LatexCommandRegistryModel.filter_indexing_newcommands(commands) == commands

    def test_excludes_a_def_defined_helper(self):
        commands = [{"name": r"\fn", "body": r"\def\fn#1#2{\footnote{#1: #2}}"}]
        assert LatexCommandRegistryModel.filter_indexing_newcommands(commands) == []

    def test_excludes_a_newcommand_that_never_calls_index(self):
        commands = [{"name": r"\bold", "body": r"\newcommand{\bold}[1]{\textbf{#1}}"}]
        assert LatexCommandRegistryModel.filter_indexing_newcommands(commands) == []

    def test_mixed_list_keeps_only_the_indexing_newcommands(self):
        indexing = {"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"}
        non_indexing = {"name": r"\bold", "body": r"\newcommand{\bold}[1]{\textbf{#1}}"}
        legacy_def = {"name": r"\fn", "body": r"\def\fn#1#2{\footnote{#1: #2}}"}

        result = LatexCommandRegistryModel.filter_indexing_newcommands([indexing, non_indexing, legacy_def])

        assert result == [indexing]

    def test_empty_list_returns_empty_list(self):
        assert LatexCommandRegistryModel.filter_indexing_newcommands([]) == []
