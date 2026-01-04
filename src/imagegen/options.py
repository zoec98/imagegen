"""Command-line options parser for imagegen.

This module builds and parses command-line options for the imagegen CLI.
It dynamically reflects the available models and their supported options from
imagegen.registry.MODEL_REGISTRY.

Usage:
- build_parser(registry) -> argparse.ArgumentParser
- parse_args(argv, registry=MODEL_REGISTRY, parser=None) -> ParsedOptions

The parse result includes:
- model: the selected model name (str)
- endpoint: model endpoint (str)
- call: call type (str)
- params: dict of input parameters assembled from common and model-specific options

Rules enforced:
- One model name must be the first positional argument.
- Exactly one of -p/--prompt or -f/--file must be provided.
- If -f/--file is given, the prompt is loaded from prompts/<name>[.txt].
- -% toggles enable_safety_checker to True; default comes from model options or False.
- -i/--image_size conflicts with -w/--width and -h/--height; when width/height is allowed,
  both must be supplied together.
- -#/--num_images is supported for models that include num_images in their options.
- --loras accepts a comma-separated list and can be provided multiple times, merged into a list.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .registry import MODEL_REGISTRY

_DOTENV_FILE = Path(".env")
_JPG_OPTION_DEFAULTS = {
    "quality": 75,
    "subsampling": 2,
    "progressive": True,
    "optimize": True,
}
_JPG_OPTION_TYPES = {
    "quality": int,
    "subsampling": int,
    "progressive": bool,
    "optimize": bool,
}


@dataclass
class ParsedOptions:
    """Structured result of parsing command-line arguments for image generation.

    Attributes:
        model: Selected model key from the registry.
        endpoint: Endpoint identifier for the model.
        call: Invocation type for the model (e.g., "subscribe", "run").
        params: Dictionary of parameters to pass to the model endpoint.
        add_prompt_metadata: Whether the CLI requested storing the prompt in EXIF.
        as_jpg: Whether to convert PNG responses into JPEG files.
        jpg_options: JPEG encoding options for PNG conversions.
        extra_metadata: Additional metadata to store in EXIF (not passed to model).
    """

    model: str
    endpoint: str
    call: str
    params: dict[str, Any]
    add_prompt_metadata: bool = False
    preview_assets: bool = True
    as_jpg: bool = True
    jpg_options: dict[str, Any] = field(
        default_factory=lambda: dict(_JPG_OPTION_DEFAULTS)
    )
    extra_metadata: dict[str, Any] = field(default_factory=dict)


def _prompt_from_file(path: Path) -> str:
    """Load prompt text from a file path and return its text content.

    Args:
        path: The resolved file system path to read.
    """
    text = path.read_text(encoding="utf-8")
    return text


def _resolve_filespec(filespec: str, base_dir: Path | None = None) -> Path:
    """Resolve a prompt filespec to a concrete file path.

    Rules:
    - If filespec contains a slash ('/'), take it literally (absolute or relative).
    - Else, if it contains a dot, resolve to prompts/filespec.
    - Else, resolve to prompts/filespec.txt.

    Args:
        filespec: The user-provided filespec following -f/--file.
        base_dir: Optional base directory to resolve relative paths; defaults to cwd.

    Returns:
        Path to the file. Raises FileNotFoundError if it does not exist.
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    if "/" in filespec:
        path = (base / filespec) if not filespec.startswith("/") else Path(filespec)
    else:
        prompts_dir = base / "prompts"
        if "." in filespec:
            path = prompts_dir / filespec
        else:
            path = prompts_dir / f"{filespec}.txt"
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path


def _default_help(name: str) -> str:
    return name.replace("_", " ")


def _get_flags_for_option(name: str, spec: Mapping[str, Any]) -> list[str]:
    base_flag = f"--{name.replace('_', '-')}"
    flags: list[str] = []
    spec_flags = spec.get("flags")
    if isinstance(spec_flags, str):
        flags.append(spec_flags)
    elif isinstance(spec_flags, (list, tuple)):
        flags.extend(spec_flags)
    if base_flag not in flags:
        flags.append(base_flag)
    return flags


def _add_prompt_arguments(
    parser: argparse.ArgumentParser, option: Mapping[str, Any]
) -> None:
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_help = option.get("help", "prompt text")
    file_help = option.get("file_help", "prompt file in prompts/")
    prompt_group.add_argument("-p", "--prompt", dest="prompt", help=prompt_help)
    prompt_group.add_argument("-f", "--file", dest="file", help=file_help)


def _parse_image_size(
    value: str, *, allowed_sizes: Sequence[str], allow_dimensions: bool
) -> str:
    candidate = value.strip()
    if not candidate:
        raise argparse.ArgumentTypeError("image size must not be empty")

    lowered = candidate.lower()
    normalized_allowed = {size.lower() for size in allowed_sizes}
    if normalized_allowed and lowered in normalized_allowed:
        return lowered

    if allow_dimensions:
        parts = lowered.split("x")
        if len(parts) == 2:
            try:
                width_val = int(parts[0])
                height_val = int(parts[1])
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    "image size must be <width>x<height> with integer values"
                ) from exc
            if width_val <= 0 or height_val <= 0:
                raise argparse.ArgumentTypeError(
                    "image size dimensions must be positive integers"
                )
            return f"{width_val}x{height_val}"

    allowed = ", ".join(sorted(normalized_allowed)) if normalized_allowed else ""
    suffix = " or <width>x<height>" if allow_dimensions else ""
    message = "image size must be"
    if allowed:
        message += f" one of {allowed}"
    if suffix:
        message += suffix
    raise argparse.ArgumentTypeError(message)


def _add_image_size_option(
    parser: argparse.ArgumentParser, option: Mapping[str, Any]
) -> None:
    allow_dimensions = bool(option.get("allow_dimensions", False))
    flags = _get_flags_for_option("image_size", option)
    allowed_sizes = option.get("allowed_sizes") or ()
    allowed_sizes = tuple(str(size) for size in allowed_sizes)
    kwargs: dict[str, Any] = {
        "dest": "image_size",
        "help": option.get("help", "image size preset"),
    }
    if allow_dimensions:
        kwargs["type"] = lambda value: _parse_image_size(
            value, allowed_sizes=allowed_sizes, allow_dimensions=True
        )
        kwargs.setdefault("metavar", "SIZE|WxH")
    else:
        kwargs["type"] = lambda value: _parse_image_size(
            value, allowed_sizes=allowed_sizes, allow_dimensions=False
        )
        kwargs.setdefault("metavar", "SIZE")
    if "metavar" in option:
        kwargs["metavar"] = option["metavar"]
    parser.add_argument(*flags, **kwargs)


def _add_boolean_option(
    parser: argparse.ArgumentParser, name: str, option: Mapping[str, Any]
) -> None:
    default = option.get("default", False)
    help_text = option.get("help", f"enable {_default_help(name)}")
    disable_help = option.get("disable_help")
    if disable_help is None:
        disable_help = f"disable {_default_help(name)}"
    flags = _get_flags_for_option(name, option)
    parser.add_argument(*flags, dest=name, action="store_true", help=help_text)
    parser.add_argument(
        f"--no-{name.replace('_', '-')}",
        dest=name,
        action="store_false",
        help=disable_help,
    )
    parser.set_defaults(**{name: default})


def _add_standard_option(
    parser: argparse.ArgumentParser, name: str, option: Mapping[str, Any]
) -> None:
    opt_type = option.get("type")
    flags = _get_flags_for_option(name, option)
    kwargs: dict[str, Any] = {"dest": name}
    if "help" in option:
        kwargs["help"] = option["help"]
    else:
        kwargs["help"] = f"set {_default_help(name)}"

    if "action" in option:
        kwargs["action"] = option["action"]
    if "metavar" in option:
        kwargs["metavar"] = option["metavar"]

    if kwargs.get("action") == "append":
        parser.add_argument(*flags, **kwargs)
        return

    if isinstance(opt_type, type) and opt_type in {int, float, str}:
        kwargs["type"] = opt_type

    parser.add_argument(*flags, **kwargs)


def _add_model_options(
    parser: argparse.ArgumentParser, options: Mapping[str, Any]
) -> None:
    prompt_spec = options.get("prompt")
    if prompt_spec and prompt_spec.get("type") == "prompt":
        _add_prompt_arguments(parser, prompt_spec)

    image_size_spec = options.get("image_size")
    if image_size_spec:
        _add_image_size_option(parser, image_size_spec)

    for dimension in ("width", "height"):
        if dimension in options:
            _add_standard_option(parser, dimension, options[dimension])

    for name, option in options.items():
        if name in {"prompt", "image_size", "width", "height"}:
            continue
        opt_type = option.get("type")
        if opt_type is bool:
            _add_boolean_option(parser, name, option)
        else:
            _add_standard_option(parser, name, option)


def _split_option_values(raw_values: Sequence[str]) -> list[str]:
    values: list[str] = []
    for item in raw_values:
        parts = [part.strip() for part in item.split(",") if part.strip()]
        values.extend(parts)
    return values


def _normalize_external_resources(
    raw_values: Sequence[str],
    *,
    base_url: str,
    default_suffix: str,
    return_with_weights: bool = False,
) -> list[str] | list[tuple[str, float]]:
    base = base_url.rstrip("/") + "/"
    normalized: list[str] | list[tuple[str, float]] = []
    for item in _split_option_values(raw_values):
        value = item
        weight = 1.0
        if return_with_weights and ";" in value:
            maybe_path, maybe_weight = value.rsplit(";", 1)
            try:
                weight = float(maybe_weight)
                value = maybe_path
            except ValueError:
                value = item
                weight = 1.0
        if "://" in value:
            final_value = value
        else:
            name = value
            if "." not in name:
                name = f"{name}{default_suffix}"
            final_value = f"{base}{name}"
        if return_with_weights:
            normalized.append((final_value, weight))
        else:
            normalized.append(final_value)
    return normalized


def get_safetensors_url() -> str:
    return os.environ.get("SAFETENSORS_URL", "https://example.com/j/")


def get_source_image_url():
    return os.environ.get("SOURCE_IMAGE_URL", "https://example.com/k/")


def _normalize_loras(raw_values: Sequence[str]) -> list[dict[str, float | str]]:
    entries = _normalize_external_resources(
        raw_values,
        base_url=get_safetensors_url(),
        default_suffix=".safetensors",
        return_with_weights=True,
    )
    normalized: list[dict[str, float | str]] = []
    for path, weight in entries:
        normalized.append({"path": path, "scale": weight})
    return normalized


def _normalize_image_urls(raw_values: Sequence[str]) -> list[str]:
    return _normalize_external_resources(
        raw_values, base_url=get_source_image_url(), default_suffix=".jpg"
    )


def _normalize_image_url(raw_value: str) -> str:
    return _normalize_image_urls([raw_value])[0]


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-a",
        "--add-prompt",
        dest="add_prompt_metadata",
        action="store_true",
        help="store the provided prompt in the image EXIF metadata",
    )
    parser.add_argument(
        "--no-preview",
        dest="preview_assets",
        action="store_false",
        default=True,
        help="do not open generated images after they are saved",
    )
    parser.add_argument(
        "--as-jpg",
        dest="as_jpg",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="save PNG responses as JPEGs",
    )
    parser.add_argument(
        "--jpg-options",
        dest="jpg_options",
        default=None,
        help=(
            "comma-separated JPEG options (quality, subsampling, progressive, optimize)"
        ),
    )
    parser.add_argument(
        "--meta",
        dest="meta",
        default=None,
        help="JSON string containing additional metadata to store in EXIF",
    )


def _build_common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    _add_common_options(parser)
    return parser


def build_parser(
    registry: Mapping[str, Mapping[str, Any]] = MODEL_REGISTRY,
) -> argparse.ArgumentParser:
    """Build the CLI argument parser with model-specific subcommands."""

    common_parser = _build_common_parser()

    parser = argparse.ArgumentParser(
        prog="imagegen",
        add_help=False,
        description="imagegen model runner",
        parents=[common_parser],
    )
    parser.add_argument("--help", action="help", help="show this help message and exit")

    model_names = sorted(registry.keys())
    subparsers = parser.add_subparsers(dest="model", metavar="model", required=True)

    for model_name in model_names:
        model_def = registry[model_name]
        options = dict(model_def.get("options", {}))
        description = f"endpoint: {model_def['endpoint']} | call: {model_def['call']}"
        model_parser = subparsers.add_parser(
            model_name,
            add_help=False,
            help=description,
            description=description,
            parents=[common_parser],
        )
        model_parser.add_argument(
            "--help", action="help", help="show this help message and exit"
        )
        _add_model_options(model_parser, options)
        model_parser.set_defaults(_model_parser=model_parser)

    return parser


def parse_args(
    argv: list[str],
    *,
    registry: Mapping[str, Mapping[str, Any]] = MODEL_REGISTRY,
    parser: argparse.ArgumentParser | None = None,
    base_dir: Path | None = None,
) -> ParsedOptions:
    """Parse argv into a ParsedOptions object."""

    load_dotenv(_DOTENV_FILE)  # silently ignore if there is none, assume defaults.

    if parser is None:
        parser = build_parser(registry)

    ns = parser.parse_args(argv)

    model_name_value = getattr(ns, "model", None)
    if not isinstance(model_name_value, str):
        parser.error("model name must be provided")
    if model_name_value not in registry:
        model_names = ", ".join(sorted(registry.keys()))
        parser.error(
            f"unknown model '{model_name_value}' - valid names are: {model_names}"
        )
    model_name = model_name_value

    model_def = registry[model_name]
    option_specs: dict[str, dict[str, Any]] = {
        key: (
            dict(value)
            if isinstance(value, Mapping)
            else {"type": None, "default": value}
        )
        for key, value in model_def.get("options", {}).items()
    }

    params: dict[str, Any] = {}
    for key, spec in option_specs.items():
        default = spec.get("default")
        if default is not None and spec.get("type") != "prompt":
            params[key] = default

    model_parser = getattr(ns, "_model_parser", parser)

    prompt_spec = option_specs.get("prompt")
    if prompt_spec and prompt_spec.get("type") == "prompt":
        if getattr(ns, "prompt", None) is not None:
            params["prompt"] = ns.prompt
            params.pop("file", None)
        elif getattr(ns, "file", None) is not None:
            file_path = _resolve_filespec(ns.file, base_dir=base_dir)
            params["file"] = str(file_path)
            params["prompt"] = _prompt_from_file(file_path)
        else:
            default_prompt = prompt_spec.get("default")
            if default_prompt is not None:
                params["prompt"] = default_prompt

    image_size_spec = option_specs.get("image_size")
    allows_dimensions = (
        image_size_spec is not None and image_size_spec.get("type") == "whi"
    )
    allows_width = "width" in option_specs
    allows_height = "height" in option_specs
    width = getattr(ns, "width", None) if allows_width else None
    height = getattr(ns, "height", None) if allows_height else None
    used_dimensions = False
    if allows_width or allows_height:
        if (width is not None) ^ (height is not None):
            model_parser.error("--width and --height must be provided together")
        if width is not None and height is not None:
            if not allows_dimensions:
                model_parser.error(
                    "--width/--height are only supported for models that allow explicit dimensions"
                )
            params["image_size"] = {"width": width, "height": height}
            used_dimensions = True

    image_size_value = getattr(ns, "image_size", None) if image_size_spec else None
    if image_size_value is not None and not used_dimensions:
        params["image_size"] = image_size_value

    if "loras" in option_specs:
        loras_values = getattr(ns, "loras", None)
        if loras_values:
            params["loras"] = _normalize_loras(loras_values)

    if "image_urls" in option_specs:
        image_urls = getattr(ns, "image_urls", None)
        if image_urls:
            params["image_urls"] = _normalize_image_urls(image_urls)

    if "image_url" in option_specs:
        image_url = getattr(ns, "image_url", None)
        if image_url:
            params["image_url"] = _normalize_image_url(image_url)

    for key, spec in option_specs.items():
        if key in {
            "prompt",
            "image_size",
            "width",
            "height",
            "loras",
            "image_urls",
            "image_url",
        }:
            continue
        opt_type = spec.get("type")
        if opt_type is bool:
            if hasattr(ns, key):
                params[key] = getattr(ns, key)
            continue

        value = getattr(ns, key, None)
        if value is not None:
            params[key] = value

    if "seed" in option_specs:
        seed_spec = option_specs["seed"]
        parsed_seed = getattr(ns, "seed", None)
        if parsed_seed is not None:
            params["seed"] = parsed_seed
        elif seed_spec.get("default") is None:
            params["seed"] = secrets.randbits(32)
        else:
            params["seed"] = seed_spec.get("default")

    if model_name == "nano-banana" and "image_size" in params:
        params["aspect_ratio"] = params.pop("image_size")

    jpg_options = _parse_jpg_options(getattr(ns, "jpg_options", None), model_parser)

    # Parse extra metadata
    extra_metadata = {}
    meta_json = getattr(ns, "meta", None)
    if meta_json:
        try:
            extra_metadata = json.loads(meta_json)
        except json.JSONDecodeError as exc:
            model_parser.error(f"invalid JSON in --meta: {exc}")

    return ParsedOptions(
        model=model_name,
        endpoint=model_def["endpoint"],
        call=model_def["call"],
        params=params,
        add_prompt_metadata=bool(getattr(ns, "add_prompt_metadata", False)),
        preview_assets=bool(getattr(ns, "preview_assets", True)),
        as_jpg=bool(getattr(ns, "as_jpg", True)),
        jpg_options=jpg_options,
        extra_metadata=extra_metadata,
    )


def _parse_jpg_options(
    raw_value: str | None, parser: argparse.ArgumentParser
) -> dict[str, Any]:
    options = dict(_JPG_OPTION_DEFAULTS)
    if not raw_value:
        return options

    for raw_entry in raw_value.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            parser.error(
                "jpg options must be key=value pairs (quality, subsampling, "
                "progressive, optimize)"
            )
        key, value = (part.strip() for part in entry.split("=", 1))
        if key not in _JPG_OPTION_DEFAULTS:
            valid = ", ".join(_JPG_OPTION_DEFAULTS.keys())
            parser.error(f"unknown jpg option '{key}' (valid options: {valid})")
        if _JPG_OPTION_TYPES[key] is bool:
            normalized = value.lower()
            if normalized in {"true", "1", "yes"}:
                options[key] = True
            elif normalized in {"false", "0", "no"}:
                options[key] = False
            else:
                parser.error(f"jpg option '{key}' expects true/false")
        else:
            try:
                options[key] = int(value)
            except ValueError:
                parser.error(f"jpg option '{key}' expects an integer")

    return options
