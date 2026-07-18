# greeting-kit

Minimal, real, buildable package used to teach the "package format + publish
to PyPI" part of the dependency-management deep dive. It only uses `hatchling`
as its build backend, so it's not tied to pip, poetry, or uv — any of them can
build and publish it.

## Build

```bash
python -m pip install build twine
python -m build          # writes dist/greeting_kit-0.1.0-py3-none-any.whl
                          # and dist/greeting_kit-0.1.0.tar.gz (sdist)
```

## Inspect what actually ships

```bash
unzip -l dist/*.whl
tar tzf dist/*.tar.gz
```

## Publish

Always rehearse on [TestPyPI](https://test.pypi.org) first — it is a separate
index with the same rules, so mistakes (bad README rendering, wrong
classifiers, a taken name) are free to fix. Package names are global and
first-come-first-served, and a given `name==version` can never be re-uploaded
once published, even to fix a bug.

```bash
# 1. create an API token at https://test.pypi.org/manage/account/token/
twine upload --repository testpypi dist/*

# 2. once you're happy, get a real-PyPI token and:
twine upload dist/*
```

## Install what you just published

```bash
pip install --index-url https://test.pypi.org/simple/ aiml-learning-gang-greeting-kit
pip install aiml-learning-gang-greeting-kit   # after the real publish
```
