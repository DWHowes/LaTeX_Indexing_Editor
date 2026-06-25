class MacroIDGenerator:
    """
    Pure Data Model.
    Generates and increments unique tracking identification keys.
    """
    def __init__(self, starting_id: int = 1):
        self._current_id = starting_id

    def get_and_increment_id(self) -> int:
        """Atomic retrieval pass for sequential ID indexing loops."""
        allocated_id = self._current_id
        self._current_id += 1
        return allocated_id

    def reset(self, starting_id: int = 1) -> None:
        """Re-seed the generator, typically called after a project is loaded."""
        self._current_id = starting_id