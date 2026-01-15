# Repository Guidelines

## Project Structure & Module Organization
- This is the code for a CLI program `imagegen`,
  and (in-progress) a Flask web application `imageedit` that will edit prompt files,
  invoke image generation, and show matching assets.
- The source for the image generator lives in `src/imagegen`; `__init__.py`
  hosts the CLI entrypoint and `options.py` drives argument parsing via the registry in `registry.py`.
  The image generator also generates an EXIF block, code for that is in `exif.py`.
- The Flask app scaffolding will live in `src/imageedit` with templates under `src/imageedit/templates`.
- As functionality becomes shared between CLI and Flask (e.g., prompt helpers, validation),
  move it into a `src/image_common/` package and import it from both call sites.
- The CLI auto-opens generated assets on macOS; pass `--no-preview` (the Flask app already does this) to skip opening.
- Tests under `tests/` mirror CLI scenarios; pair new features with matching `test_<feature>.py` modules. We always run all tests; this is fast enough.
- File prompts resolve against `prompts/`; store reusable fixtures there when a test needs disk input.

## Flask App Expectations
- Keep the README’s “Prompt editor (Flask UI)” section accurate whenever `src/imageedit` changes (commands, features, templates).
- The Flask app should continue to mirror the CLI registry: surfaced models, prompt editing, and key flags (`-a`, `-i`, `-u`, etc.) must stay in sync.
- When changing imagegen CLI flags or output behavior, update README usage notes and consider whether imageedit needs matching controls.
- Routes and templates for the app live under `src/imageedit` and `src/imageedit/templates`; update both sides when adding new UI affordances.
- Always run `uv run flask --app imageedit.app run --debug` locally before shipping Flask changes to verify the browser flow end to end.

## Build, Test, and Development Commands
- `uv run imagegen dev -p "demo prompt"` executes the CLI; swap the model key to exercise other registry entries.
- `uv run flask --app imageedit.app run --debug` runs the Flask server in development mode.
- `uv run pytest` runs the full suite; we always run all tests because this is fast enough.
- `uv run ruff format` to format the source code, run before pushing.
- `uv run ruff check --fix` to lint (and autofix) the source where needed, run before pushing.
- `uv run mypy src` typing clean; run before pushing.

## Coding Style & Naming Conventions
- Target Python 3.13+, 4-space indent, `ruff format`-formatted code; avoid manual wrapping.
- Keep helper functions pure, isolate side effects to `main()`, and favour `dataclass` records for structured results.
- Favor `pathlib` for filesystem operations where possible.
- Registry keys remain lower_snake_case and match upstream API option names.

## Testing Guidelines
- Prefer behaviour-driven `pytest` cases covering success paths and argparse errors (see `tests/test_two_pass_parser.py`).
- Use temporary directories for prompt-file tests instead of committing sample assets.
- Add regression tests whenever changing registry schema, defaults, or CLI flags.

## Commit & Pull Request Guidelines
- History shows short present-tense summaries (e.g., `Option parsing`); follow that style and stay under 60 chars.
- PRs should link tickets when relevant, describe behavioral changes, and attach CLI output if it clarifies the result.
- Verify `ruff format`, `mypy`, and `pytest` locally; we always run the full test suite because this is fast enough.
  Call out any skipped checks with justification.

## Agent-Specific Notes
- Prefer `uv run` over system Python so dependencies resolve consistently.
- Do not use `pip`, use `uv pip`.
- Try to avoid editing `pyproject.toml`, if there is an `uv` subcommand to do the same:
  `uv add dependency`, or `uv add --dev dependency`, for example.
- Never edit `uv.lock`, always use `uv lock` to update, and `uv sync` to check.
- Standard HTTP client is `httpx`; use synchronous requests unless explicitly directed to go async.
- Standard data storage is SQLite (prefer `sqlite3` unless SQLAlchemy is required).
- imageedit stores upload history and generation logs in `assets/imageedit.sqlite3`.
- For the Flask app, make use of the Flask ecosystem and use existing Flask modules where useful
  (forms, validation, sessions, etc.)
- Treat `registry.py` as the source of truth; document and test any change in available options.
