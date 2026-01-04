# imagegen — Generate images with fal.ai from the command line

imagegen is a tiny, testable Python CLI that generates images using fal.ai models and workflows. You provide a text prompt either directly on the command line or via a prompt file, choose a model, and imagegen will call fal.ai, download the results, and write them under the assets/ directory. The tool exposes each model’s options as standard CLI flags and prints the generated file paths on stdout (one per line) so it can be chained in scripts.

- Prompts come from -p/--prompt or -f/--file (files live in prompts/ and .txt is optional).
- Image size can be chosen by preset (-i) or, for supported models, by explicit width/height (-w/-h).
- Some models support extra options such as multiple images (-#), LoRAs, etc.

If you are new to this repository, start with the Quick start. If you want to add support for additional fal.ai models or workflows, see the Developer guide.


## Quick start

### Prerequisites
- Python 3.12
- uv (fast Python package manager by Astral): https://docs.astral.sh/uv/
- fal.ai account and API key (FAL_KEY)

### 1) Clone and install
```
# clone
git clone <this-repo-url>
cd Img

# install dependencies (creates .venv managed by uv)
uv sync
```

### 2) Configure your API key
Set your fal.ai API key in the environment. The CLI auto-loads .env if python-dotenv is available.

- Option A: create a .env file at the project root (**recommended**)
```
FAL_KEY=your_fal_api_key
```
- Option B: export in your shell
```
export FAL_KEY=your_fal_api_key
```


### 3) Run imagegen (CLI)

- List available models and general usage:
```
uv run imagegen --help
```

- Get help for a specific model (shows that model’s options):
```
uv run imagegen <model-name> --help
```

- Example run:
```
uv run imagegen seedream -f cookie
```
Note: seedream is an example model name.
Use uv run imagegen --help to see the models registered in this repository (e.g., schnell, dev, flux-2, flux-2-pro, nano-banana, …).
To run with a prompt file, place prompts/cookie.txt in the prompts/ directory
(the .txt suffix is optional when using -f cookie).

- A concrete example with a built‑in model:
```
# Single image with a prompt string
uv run imagegen schnell -p "a watercolor of a red fox in a birch forest"

# Generate 2 images using the dev model
uv run imagegen dev -p "detailed city skyline at dusk" -# 2

# If the model supports width/height (dev does), you can specify both -w and -h
uv run imagegen dev -p "studio photo" -w 832 -h 1216

# Use the Flask prompt editor (imageedit) if you prefer a UI
uv run flask --app imageedit.app run --debug
```

When generation succeeds, image paths are printed to stdout and the files are written under assets/
(e.g., assets/schnell-1.png).
This makes it easy to capture them in scripts:
```
paths=$(uv run imagegen schnell -p "stained glass hummingbird")
for p in $paths; do open "$p"; done
```

On MacOS, imagegen will auto-open images when their generation is completed.
Pass `--no-preview` to suppress this behavior (useful in scripts or when running headless).


## imagegen (CLI)

### How prompts and files are resolved
- -p/--prompt supplies the text inline.
- -f/--file looks under prompts/. You can pass either name or name.txt.
  - Example: -f cookie resolves to prompts/cookie.txt
  - You can also pass a path containing a slash (e.g., subdir/cookie.txt) to point to a specific file.

Exactly one of -p or -f must be provided.


### Image size and dimensions
- -i/--image-size picks a preset. Supported values include: square_hd, square, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9.
- Some models allow explicit -w/--width and -h/--height instead of -i.
  - If a model allows dimensions, you must provide both -w and -h, and you must not pass -i.
  - Some models also allow WIDTHxHEIGHT syntax as a value to -i (see per‑model help).

To see what a model supports, run:
```
uv run imagegen <model-name> --help
```


### Output
- Images are downloaded to assets/ with a model‑and‑index‑based filename.
- The CLI prints the final file paths to stdout, one per line, and nothing else. This is intentional so that other tools can consume the output reliably.
- On macOS the files auto-open after download unless `--no-preview` is supplied.


### Troubleshooting
- No models appear or calls fail: ensure FAL_KEY is set (env var or .env) and that your fal.ai account has access to the chosen model/workflow.
- Prompt file not found: make sure the file exists under prompts/ and that you used the correct name (with or without .txt). For nested paths, include the slash (e.g., -f sub/idea.txt).
- Width/height errors: only use -w and -h together, and only for models that support dimensions; otherwise, use -i.
- Multiple images: use -#/--num-images if the model supports it (check per‑model help).
- Need to skip automatic previews: append `--no-preview` to any command; it works with every model.
- PNG outputs are saved as JPEG by default; use `--no-as-jpg` to keep PNGs, or `--jpg-options="quality=60,progressive=False"` to customize JPEG encoding.


## imageedit (Flask UI)

A companion Flask app, `imageedit`, lets you manage prompt and style files and trigger runs from the browser. The UI is API-driven (AJAX) and mirrors the CLI registry so model options stay in sync.

Features
- Prompt CRUD backed by `prompts/` (save, duplicate, delete) with modal confirmations.
- Style CRUD backed by `styles/`, plus quick insert into the prompt editor.
- Model selection and preset size selector synced to the registry via `/api/model-sizes`.
- Optional source image URLs (`-u`) with local file uploads sent to fal storage.
- Asset gallery with EXIF-based prompt reload and quick delete.
- Runs invoke the CLI pipeline with `--no-preview` and surface generated assets.

### Running the app
- Start a local dev server:
```
uv run flask --app imageedit.app run --debug
```
- Or use the helper script (binds to 0.0.0.0:5002):
```
./start_flask.sh
```

### Environment and storage
- imageedit uses the same `FAL_KEY` env var as the CLI because it calls the same fal.ai client.
- Prompts are stored under `prompts/`, styles under `styles/`, and generated assets under `assets/`.

### Security considerations
This Flask app has no authentication or network security. It is intended for localhost use or trusted networks only. If you bind to 0.0.0.0 (including `./start_flask.sh`), anyone on the network can access it. Treat it as a development tool unless you add your own protections.

---

# Developer guide — adding fal.ai models and workflows

This section targets contributors who want to expose additional fal.ai endpoints in the CLI. The CLI reflects models from a single registry in code; to add a model or workflow, extend the registry and follow the option schema described below.

## Where to add models
- Edit src/imagegen/registry.py
- The top‑level dict MODEL_REGISTRY defines each model/workflow entry.

Each entry looks like this (simplified):

```python
MODEL_REGISTRY = {
    "schnell": {
        "endpoint": "fal-ai/flux/schnell",   # as listed on fal.ai
        "call": "subscribe",                 # how to invoke via fal client (e.g., "subscribe" or "run")
        "doc_url": "https://fal.ai/models/fal-ai/flux/schnell/api#schema",
        "options": {
            "prompt": {
                "type": "prompt",           # special type: requires -p or -f
                "default": None,
                "help": "prompt text",
                "file_help": "prompt file in prompts/",
            },
            "image_size": {
                "type": "i",                # presets only; or "whi" for WIDTHxHEIGHT support
                "default": "portrait_4_3",
                "flags": ["-i", "--image-size"],
                "help": "preset image size",
            },
            # Additional options… see below
        },
    },
}
```

## Option schema (how CLI flags are generated)
Options declared under options: are converted to argparse flags by src/imagegen/options.py.

Common fields:
- type: one of
  - "prompt" — special option enabling -p/--prompt and -f/--file, enforcing that exactly one is provided.
  - "i" — image size presets via -i/--image-size.
  - "whi" — enables preset handling AND explicit dimensions; when set, -w/--width and -h/--height can be added as separate options to the model.
  - int, float, str, bool — standard types become flags automatically (names are turned into --kebab-case; you can add short flags via flags).
- default: default value for the option.
- help: help text for argparse.
- flags: optional list of CLI flags. Examples: ["-#", "--num-images"], ["-s", "--seed"]. If omitted, a default --kebab-case flag is generated.
- disable_help: for boolean flags that act as toggles (e.g., enable_safety_checker) the help for on/off can be customized.

Special options and behaviors implemented in options.py:
- Prompts: Exactly one of -p/--prompt or -f/--file is required.
- Prompt files: -f resolves into prompts/<name>[.txt] unless the value contains a slash, in which case it’s treated as a path.
- Image sizes: -i conflicts with -w/-h. If a model supports dimensions, both -w and -h must be provided together.
- Multiple images: models can declare num_images with flags ["-#", "--num-images"].
- LoRA lists and external resources: some models support lists (see _normalize_loras and friends in options.py for details if you add such options).

## How invocation works
- The parsed options are assembled into a ParsedOptions dataclass by parse_args.
- src/imagegen/imagegen.py reads ParsedOptions and calls fal_client using the endpoint and call method defined in the registry entry.
- Results are streamed, URLs are downloaded, and files are stored under assets/ with sanitized names. The CLI prints those file paths to stdout.

## Steps to add a new model/workflow
1. Identify the fal.ai endpoint and invocation type (subscribe vs run) and add an entry under MODEL_REGISTRY with endpoint, call, and doc_url.
2. Define options that map to the model’s inputs following the schema above. Reuse patterns from existing models (e.g., schnell, dev).
3. If your model supports WIDTHxHEIGHT, set image_size.type to "whi" and add width and height options with types int and flags ["-w", "--width"], ["-h", "--height"].
4. If the model supports multiple images, add a num_images option with flags ["-#", "--num-images"].
5. Run help to verify the UX:
   - uv run imagegen <your-model> --help
6. Try an end‑to‑end call with a small prompt to confirm the API contract.

## Testing and quality
- All functions should be testable. New logic should come with pytest tests under tests/.
- Run tests:
```
uv run pytest -q
```
- Linting and type checking (if configured in pyproject.toml):
```
uv run ruff check
uv run ruff format --check
uv run pyright  # or "ty" if used in this repo
```

## Releasing changes
- Keep README.md and inline docstrings up to date.
- Prefer minimal, composable options so the CLI help stays readable.


## Reference
- fal.ai: https://fal.ai
- uv docs: https://docs.astral.sh/uv/
