"""Demo package managed by Poetry.

Typical workflow:
    poetry install          # creates .venv, installs deps + this package (editable)
    poetry add httpx         # add a new runtime dependency, updates pyproject.toml + poetry.lock
    poetry add --group dev pytest  # dev-only dependency
    poetry run python -c "import dep_demo; print(dep_demo.hello())"
    poetry build             # produces dist/*.whl and dist/*.tar.gz
    poetry publish            # uploads to PyPI (needs POETRY_PYPI_TOKEN_PYPI or `poetry config`)
"""


def hello() -> str:
    return "hello from a poetry-managed package"
