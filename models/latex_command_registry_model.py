import re
from typing import List, Dict
from PySide6.QtCore import QSettings

class LatexCommandRegistryModel:
    SETTINGS_GROUP = "latex_commands"

    _NEWCOMMAND_START_RE = re.compile(r'^\s*\\(?:newcommand|renewcommand|providecommand)\*?\s*\{')
    _INDEX_CALL_RE = re.compile(r'\\index\s*[\{\[]')

    def __init__(self):
        self.settings = QSettings()
        self.settings.setFallbacksEnabled(False)

    def _open_group(self):
        self.settings.beginGroup(self.SETTINGS_GROUP)

    def _close_group(self):
        self.settings.endGroup()

    def list_commands(self) -> List[Dict[str, str]]:
        self._open_group()
        commands = [
            {"name": key, "body": str(self.settings.value(key, "", str))}
            for key in self.settings.childKeys()
        ]
        self._close_group()
        return commands

    def save_command(self, name: str, body: str) -> None:
        self._open_group()
        self.settings.setValue(name, body)
        self._close_group()
        self.settings.sync()

    def remove_command(self, name: str) -> None:
        self._open_group()
        self.settings.remove(name)
        self._close_group()
        self.settings.sync()

    def clear_commands(self) -> None:
        self._open_group()
        for key in self.settings.childKeys():
            self.settings.remove(key)
        self._close_group()
        self.settings.sync()

    def command_exists(self, name: str) -> bool:
        self._open_group()
        exists = self.settings.contains(name)
        self._close_group()
        return exists

    @staticmethod
    def filter_indexing_newcommands(commands: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Filters a list of {"name","body"} custom-command dicts (e.g. from
        LatexCommandRegistryModel.list_commands() or
        FileTreePersistence.fetch_project_custom_commands()) down to genuine
        "custom indexing commands" -- \\newcommand/\\renewcommand/\\providecommand
        wrappers whose body actually invokes \\index{...} or \\index[...].
        Excludes \\def-defined helpers (e.g. a footnote-marker formatter like
        \\def\\fn#1#2{...}) and unrelated newcommands that don't call \\index.
        """
        return [
            command for command in commands
            if LatexCommandRegistryModel._NEWCOMMAND_START_RE.match(command.get("body", ""))
            and LatexCommandRegistryModel._INDEX_CALL_RE.search(command.get("body", ""))
        ]