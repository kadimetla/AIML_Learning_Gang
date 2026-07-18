# dep-demo (uv)

Demo package used in the dependency-management slides.

```bash
uv sync                 # creates .venv + installs deps, writes uv.lock
uv add httpx             # add a runtime dependency
uv add --dev pytest       # add a dev-only dependency
uv run python -c "import dep_demo; print(dep_demo.hello())"
uv build                  # produces dist/*.whl and dist/*.tar.gz
uv publish                 # uploads to PyPI (needs UV_PUBLISH_TOKEN)
```
