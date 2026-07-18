def greet(name: str) -> str:
    """Return a friendly greeting for ``name``."""
    if not name:
        raise ValueError("name must not be empty")
    return f"Hello, {name}! This package made it to PyPI."
