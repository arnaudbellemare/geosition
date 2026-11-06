# Contributing to GEOSITION

Thanks for helping improve GEOSITION. Issues, documentation improvements, bug fixes, and focused features are welcome. For larger changes, open an issue first so we can agree on the approach.

GEOSITION is source-available under the terms in [LICENSE](../LICENSE). Please read the license before using, modifying, or redistributing the project.

## Set up locally

Fork the repository, clone your fork, and install the Python development dependencies:

```bash
git clone https://github.com/YOUR_USERNAME/geosition.git
cd geosition
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
git switch -c fix/short-description
```

Python 3.9 or newer is required. Run `geo --help` to explore the CLI. For other setup options, see the [documentation](../docs/index.md).

## Find your way around

- `src/geo_optimizer/core/`: audit and scoring logic
- `src/geo_optimizer/cli/`: commands and output formatting
- `src/geo_optimizer/web/` and `src/geo_optimizer/saas/`: web app and platform services
- `tests/`: automated tests
- `docs/`: guides, research references, and project plans
- `apps/`: additional applications with their own setup instructions

See the [repository map](../docs/repository-map.md) for the complete layout. Keep core logic separate from presentation, use the shared configuration for scoring constants, and preserve Python 3.9 compatibility. URL fetching and validation are security-sensitive; retain the existing protections when changing them.

## Check your changes

Run the relevant tests and the Python checks used by CI:

```bash
pytest tests/ -q
ruff check src/geo_optimizer/
ruff format --check src/geo_optimizer/
```

For changes to repository SEO data, also run `npm ci` and `npm run seo:verify`. Changes to the tracker under `apps/geo-aeo-tracker/` need its own build; see its README and the [CI workflow](workflows/ci.yml). Add or update tests when behavior changes, and mock network calls in normal tests.

### Local hooks

Install `pre-commit`, `gitleaks`, ShellCheck, Node.js, and Python, then run `pre-commit install`. Install the repository's pre-push check with `python3 scripts/install-pre-push.py`. The commit checks scan changed text files for secrets, validate Python, JavaScript, JSON and shell syntax, lint shell scripts, and check Python source with Ruff. The push hook runs these checks on files changed by the pushed commits. CI runs the complete test and build suites.

## Open a pull request

1. Keep the change focused and describe the problem it solves.
2. Include relevant tests, documentation, and screenshots for visual changes.
3. Summarize the checks you ran and any limitations reviewers should know about.
4. Update [the changelog](../docs/CHANGELOG.md) when the change is user-facing.

Use descriptive commit messages; Conventional Commits are appreciated. Please avoid including credentials, customer data, audit reports, or local databases in a pull request. `.gitignore` helps exclude common local outputs, but review `git status` and your diff before committing.

## Report a problem

For bugs, [open an issue](https://github.com/arnaudbellemare/geosition/issues) with steps to reproduce, expected and actual behavior, and your operating system and Python version. Use fictional or public examples and remove private data from logs and reports.

For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue. Plugin authors can start with the [example plugin](../examples/).
