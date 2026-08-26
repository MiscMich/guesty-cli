# Contributing

Thanks for contributing to `guesty-cli`.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]' build twine
```

## Before submitting a change

```bash
python -m pytest -q
python -m build
python -m twine check dist/*
```

Keep runtime code compatible with the Python versions declared in `pyproject.toml`. Add regression tests for bug fixes. Do not use live Guesty credentials or customer data in tests, fixtures, examples, issues, or pull requests.

## Safety expectations

- Mutating commands should offer a dry-run or require explicit confirmation.
- Non-interactive mode must not weaken credential or write safeguards.
- Never log access tokens, client secrets, guest data, or account exports.
- Use obvious placeholders for account, listing, reservation, and personal data.
- Link to official API documentation instead of copying third-party documentation into the repository unless redistribution rights are confirmed by the maintainers.

## Pull requests

Keep changes focused and explain user-visible behavior. Include test output and call out any compatibility or security implications. By contributing, you agree that your contribution is licensed under the repository's MIT license.
