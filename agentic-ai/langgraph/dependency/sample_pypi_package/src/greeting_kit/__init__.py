"""greeting_kit — the minimal package that ships all the way to PyPI.

Build (works no matter which dependency tool you prefer):
    python -m pip install build twine
    python -m build                 # -> dist/*.whl + dist/*.tar.gz
    # or, equivalently:
    uv build
    poetry build

Publish:
    twine upload --repository testpypi dist/*   # rehearse on TestPyPI first
    twine upload dist/*                          # the real PyPI, once you're sure
    # or, equivalently:
    uv publish
    poetry publish
"""

from .core import greet

__all__ = ["greet"]
__version__ = "0.1.0"
