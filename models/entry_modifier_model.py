from PySide6.QtCore import QObject, Signal

class EntryModifierModel(QObject):
    """
    Core Model Layer matching View and Controller structural design patterns.
    Manages raw LaTeX indexing records independent of any UI presentation.
    """
    # Naming convention aligned directly with controller endpoints
    entry_modifier_reloaded = Signal(list)  # Emits fresh records list [ (id, main, sub1, sub2), ... ]
    entry_modifier_updated = Signal(int, bool)  # entry_id, success_status

    def __init__(self, database_persistence=None):
        super().__init__()
        self.persistence = database_persistence
        # Mock in-memory records database dictionary
        self._records = {
            1: ("Introduction", "Background", "History"),
            2: ("Methodology", "Sampling", "Size"),
            3: ("Analysis", "Statistical Models", "ANOVA")
        }

    def fetch_entry_modifier_records(self) -> list:
        """Retrieves and packages index primitives for controller pipeline dispatch."""
        return [(entry_id, *fields) for entry_id, fields in self._records.items()]

    def update_entry_modifier_field(self, entry_id: int, field_name: str, dynamic_value: str) -> bool:
        """
        Executes domain business validation logic and pushes record updates to storage.
        Returns True if successful, False if validation blocks the commit.
        """
        if entry_id not in self._records:
            return False

        # Apply domain constraints (e.g., Main field cannot be empty string)
        if field_name == "Main" and not dynamic_value.strip():
            return False

        main, sub1, sub2 = self._records[entry_id]
        
        # Maps string columns back down onto structural tuples
        if field_name == "Main": main = dynamic_value
        elif field_name == "Sub1": sub1 = dynamic_value
        elif field_name == "Sub2": sub2 = dynamic_value

        self._records[entry_id] = (main, sub1, sub2)
        
        # Notify tracking controllers that changes are committed
        self.entry_modifier_updated.emit(entry_id, True)
        return True
