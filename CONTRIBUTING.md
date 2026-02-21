# Contributing to gh-reviewers-graph

This document provides guidelines and instructions for contributing to gh-reviewers-graph development.

## Development Setup

### Prerequisites

- Python 3.10+
- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated
- Git

### Getting Started

1. Fork and clone the repository:

```bash
git clone https://github.com/gh-tui-tools/gh-reviewers-graph.git
cd gh-reviewers-graph
```

2. Install commit hooks:

   The repository contains a file called `.pre-commit-config.yaml` that defines "commit hook" behavior to be run locally in your environment each time you commit a change to the sources. To enable that "commit hook" behavior, first follow the installation instructions at https://pre-commit.com/#install, and then run this:

   ```bash
   pre-commit install
   ```

   This sets up two hooks:

   - **ruff** — lints and auto-fixes issues (`ruff check --fix`)
   - **ruff-format** — checks formatting (`ruff format`)

3. Install dependencies:

```bash
pip install .[test,lint]
```

4. Run tests:

```bash
pytest tests/ -v
```

## Development Workflow

### Testing Locally

To test the extension locally without installing it:

```bash
./gh-reviewers-graph mdn/content
```

Or install it as a local extension:

```bash
gh extension install .
gh reviewers-graph mdn/content
```

### Running Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run specific test file (--no-cov skips coverage)
pytest tests/test_fetch.py -v --no-cov

# Run e2e tests (requires Playwright)
playwright install chromium
pytest tests/e2e/ -m e2e -v --no-cov
```

### Code Quality

```bash
# Run linter
ruff check gh-reviewers-graph tests/

# Check formatting
ruff format --check gh-reviewers-graph tests/

# Run all pre-commit hooks against all files
pre-commit run --all-files
```

## Making Changes

### Branch Naming

- Feature: `feature/description`
- Bug fix: `fix/description`
- Documentation: `docs/description`

### Commit Messages

Use [conventional commit](https://www.conventionalcommits.org/) prefixes. [Refined GitHub](https://github.com/refined-github/refined-github) renders these as colored labels:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation
- `test:` add or update tests
- `refactor:` code restructuring (no behavior change)
- `ci:` CI/CD changes
- `build:` build system or dependencies
- `perf:` performance improvement
- `style:` formatting (no code change)
- `chore:` maintenance
- `revert:` revert a previous commit

### Pull Request Process

1. Create a new branch for your changes
2. Make your changes with clear, descriptive commits
3. Add or update tests as needed
4. Ensure all tests pass: `pytest tests/ -v`
5. Ensure code passes lint and format checks: `pre-commit run --all-files`
6. Push your branch and create a pull request
7. Describe your changes in the PR description
8. Wait for review and address any feedback

## Project Structure

```
.
├── gh-reviewers-graph           # Main script (single-file CLI extension)
├── page-template.html           # Page template (HTML + CSS + JS)
├── pyproject.toml               # Project metadata and tool configuration
├── .pre-commit-config.yaml      # Pre-commit hook configuration
├── schema.json                  # JSON Schema for data.json cache format
├── .github/workflows/
│   ├── ci.yml                   # CI workflow (lint + test)
│   └── update-pages.yml         # GitHub Pages deployment
├── repos/                       # Tracked repo data (gitignored outputs)
├── tests/
│   ├── conftest.py              # importlib loader and shared fixtures
│   ├── test_graphql.py          # GraphQL request handling (subprocess)
│   ├── test_cli.py              # Argument parsing
│   ├── test_main.py             # Integration tests for main()
│   ├── test_fetch.py            # Data fetching functions
│   ├── test_aggregation.py      # Output data model
│   ├── test_bot_filter.py       # Bot detection
│   ├── test_cache.py            # Cache I/O and versioning
│   ├── test_month_ranges.py     # Date range generation
│   ├── test_output.py           # Output file generation
│   ├── test_rate_limit.py       # Rate limit estimation and countdown
│   ├── test_schema.py           # JSON Schema validation
│   └── e2e/                     # Playwright end-to-end tests
├── DESIGN.md                    # Design decisions and architecture
├── README.md                    # User-facing documentation
└── CONTRIBUTING.md              # This file
```

## Testing Guidelines

- Write tests for all new functionality
- Aim for good test coverage (the project enforces a 99% threshold)
- Test edge cases and error conditions

### Coverage Reporting

The test suite enforces a **99% coverage threshold** (`fail_under = 99` in `pyproject.toml`). Lines that are genuinely untestable are marked with `# pragma: no cover`.

```bash
# Run tests with coverage report
pytest tests/
```

Coverage is configured in `pyproject.toml` and runs automatically with `pytest`.

## Reporting Issues

When reporting issues:

1. Use the issue tracker
2. Provide a clear title and description
3. Include steps to reproduce
4. Specify your environment (OS, Python version, `gh` version)
5. Include relevant error messages or output

## Questions?

Feel free to open an issue for any questions or discussions about contributing.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
