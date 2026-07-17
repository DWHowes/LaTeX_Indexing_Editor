"""MacroIDGenerator -- pure sequential id counter, no PySide6 dependency."""
from models.macro_id_generator import MacroIDGenerator


def test_default_starts_at_one():
    gen = MacroIDGenerator()
    assert gen.get_and_increment_id() == 1
    assert gen.get_and_increment_id() == 2


def test_custom_starting_id():
    gen = MacroIDGenerator(starting_id=100)
    assert gen.get_and_increment_id() == 100
    assert gen.get_and_increment_id() == 101


def test_reset_reseeds_the_counter():
    gen = MacroIDGenerator(starting_id=1)
    gen.get_and_increment_id()
    gen.get_and_increment_id()

    gen.reset(starting_id=50)

    assert gen.get_and_increment_id() == 50


def test_reset_defaults_to_one():
    gen = MacroIDGenerator(starting_id=50)
    gen.reset()
    assert gen.get_and_increment_id() == 1
