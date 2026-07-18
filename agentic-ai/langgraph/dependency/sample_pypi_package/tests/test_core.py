import pytest

from greeting_kit import greet


def test_greet():
    assert greet("Ada") == "Hello, Ada! This package made it to PyPI."


def test_greet_empty_name_raises():
    with pytest.raises(ValueError):
        greet("")
