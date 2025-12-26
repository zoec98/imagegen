import argparse

import pytest

from imagegen.options import (
    build_parser,
    get_safetensors_url,
    get_source_image_url,
    parse_args,
)
from imagegen.registry import MODEL_REGISTRY

pytestmark = pytest.mark.usefixtures("test_env_file")


@pytest.fixture()
def cwd_tmp_prompts(tmp_path, monkeypatch):
    # create prompts directory with sample files
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "cats.txt").write_text("a photo of two cats on a sofa")
    (prompts / "keks.prompt").write_text("a delicious cookie")
    # create top-level file for slash resolution tests
    (tmp_path / "plain.txt").write_text("plain text prompt")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_registry_structure():
    """Validates registry schema for each model and absence of legacy keys.

    Why: The CLI builds its parser from this metadata. Missing fields or
    lingering legacy keys ('allowed', 'defaults') would break parsing or
    misconfigure options.
    """
    for name, model in MODEL_REGISTRY.items():
        assert "options" in model and isinstance(model["options"], dict), (
            f"model {name} missing options"
        )
        assert "doc_url" in model and model["doc_url"].startswith("https://"), (
            f"model {name} missing doc_url"
        )
        assert "allowed" not in model, f"model {name} still has 'allowed'"
        assert "defaults" not in model, f"model {name} still has 'defaults'"
        for opt_name, opt_spec in model["options"].items():
            assert "type" in opt_spec, f"option {opt_name} in {name} missing type"
            assert "default" in opt_spec, f"option {opt_name} in {name} missing default"
            assert "help" in opt_spec, f"option {opt_name} in {name} missing help text"
            if opt_name == "image_size":
                assert opt_spec["type"] in {"i", "whi"}
            if opt_spec["type"] == "prompt":
                assert opt_spec["default"] is None or isinstance(
                    opt_spec["default"], str
                )
                assert "file_help" in opt_spec, (
                    f"prompt option in {name} missing file_help"
                )


def test_parser_does_not_require_common_keys():
    """Ensures parser works from typed option metadata without hidden requires.

    Why: Models may define only a subset of common options. The parser must not
    implicitly require unrelated keys; it should rely solely on the provided
    typed option specs and still apply common defaults like seed/image_size.
    """
    # Build a minimal registry ensuring parser consumes typed option metadata
    reg = {
        "foo": {
            "endpoint": "fal-ai/flux/foo",
            "call": "subscribe",
            "doc_url": "https://fal.ai/models/fal-ai/flux/foo/api#schema",
            "options": {
                "prompt": {
                    "type": "prompt",
                    "default": None,
                    "help": "prompt text",
                    "file_help": "prompt file",
                },
                "num_inference_steps": {
                    "type": int,
                    "default": 5,
                    "help": "number of diffusion steps",
                },
                "image_size": {
                    "type": "i",
                    "default": "portrait_4_3",
                    "help": "preset image size",
                    "flags": ["-i"],
                },
                "seed": {
                    "type": int,
                    "default": None,
                    "help": "random seed",
                    "flags": ["-s"],
                },
                "enable_safety_checker": {
                    "type": bool,
                    "default": False,
                    "help": "enable safety checker",
                    "disable_help": "disable safety checker",
                    "flags": ["-%"],
                },
            },
        }
    }
    parser = build_parser(reg)
    ns = parse_args(["foo", "-p", "hello"], registry=reg, parser=parser)
    # Common defaults are applied and prompt parsed
    assert ns.model == "foo"
    assert ns.params["prompt"] == "hello"
    assert ns.params["image_size"] == "portrait_4_3"
    assert isinstance(ns.params["seed"], int)


@pytest.mark.parametrize(
    "argv,expected",
    [
        (
            ["schnell", "-p", "hello world", "-i", "square", "-%"],
            {
                "model": "schnell",
                "params": {
                    "prompt": "hello world",
                    "image_size": "square",
                    "enable_safety_checker": True,
                    "num_inference_steps": 4,  # default from registry
                },
            },
        ),
        (
            ["dev", "-p", "hi", "-#", "3"],
            {
                "model": "dev",
                "params": {
                    "prompt": "hi",
                    "num_images": 3,
                    "num_inference_steps": 28,
                    "guidance_scale": 3.5,
                    "enable_safety_checker": False,
                },
            },
        ),
    ],
)
def test_parse_basic(argv, expected):
    """Covers core parsing for representative models and defaults.

    Why: Ensures command-line args are translated into model name and params,
    including model defaults and common flags, which is foundational for all
    image generation calls.
    """
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(argv, registry=MODEL_REGISTRY, parser=parser)
    assert ns.model == expected["model"]
    # All expected params should be present with expected values
    for k, v in expected["params"].items():
        assert ns.params[k] == v


def test_prompt_from_file(cwd_tmp_prompts):
    """Resolves -f prompt files under prompts/ and populates prompt text.

    Why: Users often store prompts in files; the CLI must locate them by
    basename and load content into the prompt parameter while recording the
    resolved file path for traceability.
    """
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(["schnell", "-f", "cats"], registry=MODEL_REGISTRY, parser=parser)
    assert ns.params["prompt"].startswith("a photo of two cats")
    # file path must be set and point into prompts/cats.txt
    assert ns.params["file"].endswith("prompts/cats.txt")


def test_add_prompt_flag_sets_metadata_request():
    parser = build_parser(MODEL_REGISTRY)
    enabled = parse_args(
        ["schnell", "-p", "hello world", "-a"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    disabled = parse_args(
        ["schnell", "-p", "hello world"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert enabled.add_prompt_metadata is True
    assert disabled.add_prompt_metadata is False


def test_no_preview_flag_disables_preview():
    parser = build_parser(MODEL_REGISTRY)
    disabled = parse_args(
        ["schnell", "-p", "hello world", "--no-preview"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    enabled = parse_args(
        ["schnell", "-p", "hello world"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert disabled.preview_assets is False
    assert enabled.preview_assets is True


def test_as_jpg_flag_defaults_on_and_can_be_disabled():
    parser = build_parser(MODEL_REGISTRY)
    enabled = parse_args(
        ["schnell", "-p", "hello world"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    disabled = parse_args(
        ["schnell", "-p", "hello world", "--no-as-jpg"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert enabled.as_jpg is True
    assert disabled.as_jpg is False


def test_jpg_options_override_defaults():
    parser = build_parser(MODEL_REGISTRY)
    parsed = parse_args(
        [
            "schnell",
            "-p",
            "hello world",
            "--jpg-options",
            "optimize=False,progressive=False,quality=60,subsampling=0",
        ],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert parsed.jpg_options == {
        "quality": 60,
        "subsampling": 0,
        "progressive": False,
        "optimize": False,
    }


def test_jpg_options_reject_invalid_key():
    parser = build_parser(MODEL_REGISTRY)
    with pytest.raises(SystemExit):
        parse_args(
            ["schnell", "-p", "hello world", "--jpg-options", "fantasy=17"],
            registry=MODEL_REGISTRY,
            parser=parser,
        )


def test_help_includes_common_options():
    parser = build_parser(MODEL_REGISTRY)
    help_text = parser.format_help()
    assert "--no-preview" in help_text
    assert "--no-as-jpg" in help_text
    assert "--jpg-options" in help_text
    # Inspect one model parser help to ensure common options surface there too
    subparsers_action = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)  # type: ignore[attr-defined]
    )
    schnell_parser = subparsers_action.choices["schnell"]
    assert "--no-preview" in schnell_parser.format_help()


def test_width_height_with_image_size_ok_and_precedence():
    """Allows -w/-h with -i for supported models; width/height take precedence.

    Why: Some models accept explicit dimensions. When both presets (-i) and
    explicit size (-w/-h) are present, the parser should prefer explicit values;
    it should also enforce that width and height are provided together.
    """
    # Use a model that supports width/height (dev)
    parser = build_parser(MODEL_REGISTRY)
    # -i with -w/-h should be allowed; width/height take precedence and image_size ignored
    ns = parse_args(
        ["dev", "-p", "x", "-i", "square", "-w", "1024", "-h", "768"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert ns.params["image_size"] == {"width": 1024, "height": 768}
    # Missing one of -w/-h should error when any is provided
    with pytest.raises(SystemExit):
        parse_args(
            ["dev", "-p", "x", "-w", "1024"], registry=MODEL_REGISTRY, parser=parser
        )


def test_loras_list_parsing():
    """Parses repeated --loras and normalizes comma lists to URL list.

    Why: Users can provide multiple LoRAs across flags or as comma-separated
    values. The parser must produce an ordered list of fully-qualified
    safetensors URLs.
    """
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(
        ["krea-lora", "-p", "x", "--loras", "a,b", "--loras", "c"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    base = get_safetensors_url().rstrip("/") + "/"
    assert ns.params["loras"] == [
        {"path": f"{base}a.safetensors", "scale": 1},
        {"path": f"{base}b.safetensors", "scale": 1},
        {"path": f"{base}c.safetensors", "scale": 1},
    ]


def test_loras_weight_parsing():
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(
        [
            "krea-lora",
            "-p",
            "x",
            "--loras",
            "https://example.com/a.safetensors;1.2",
            "--loras",
            "b;0.5",
        ],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    base = get_safetensors_url().rstrip("/") + "/"
    assert ns.params["loras"] == [
        {"path": "https://example.com/a.safetensors", "scale": 1.2},
        {"path": f"{base}b.safetensors", "scale": 0.5},
    ]


def test_image_url_normalization():
    """Normalizes image URLs: expands bare names to base URL, keeps absolute.

    Why: Edit workflows require source images. The parser should help by
    resolving short names to a configured source images base while preserving
    already-absolute URLs.
    """
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(
        [
            "seedream-edit",
            "-p",
            "x",
            "--image-url",
            "keks,cookie.jpg",
            "--image-url",
            "https://example.com/bla.jpg",
        ],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    base = get_source_image_url().rstrip("/") + "/"
    assert ns.params["image_urls"] == [
        f"{base}keks.jpg",
        f"{base}cookie.jpg",
        "https://example.com/bla.jpg",
    ]


def test_file_resolution_variants(cwd_tmp_prompts):
    """Resolves -f filespec by rules: slashes literal, dot => prompts/, bare => .txt.

    Why: The CLI supports convenient shorthand for prompt files. This test locks
    down the path resolution semantics to avoid regressions that would break
    users' existing prompts.
    """
    parser = build_parser(MODEL_REGISTRY)
    # 4.1: contains a slash -> literal relative path
    ns = parse_args(
        ["schnell", "-f", "./plain.txt"], registry=MODEL_REGISTRY, parser=parser
    )
    assert ns.params["file"].endswith("plain.txt")
    assert ns.params["prompt"] == "plain text prompt"
    # 4.1: absolute path
    abs_path = str((cwd_tmp_prompts / "plain.txt").absolute())
    ns = parse_args(["schnell", "-f", abs_path], registry=MODEL_REGISTRY, parser=parser)
    assert ns.params["file"] == abs_path
    # 4.2.1: has dot, no slash -> prompts/filespec
    ns = parse_args(
        ["schnell", "-f", "keks.prompt"], registry=MODEL_REGISTRY, parser=parser
    )
    assert ns.params["file"].endswith("prompts/keks.prompt")
    assert ns.params["prompt"] == "a delicious cookie"
    # 4.2.2: no dot, no slash -> prompts/filespec.txt
    ns = parse_args(["schnell", "-f", "cats"], registry=MODEL_REGISTRY, parser=parser)
    assert ns.params["file"].endswith("prompts/cats.txt")


def test_top_level_help_lists_models(capsys):
    """CLI --help should list all available models for quick discovery.

    Why: Users need to see supported models without reading source; ensures help
    output remains informative as registry evolves.
    """
    parser = build_parser(MODEL_REGISTRY)
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    help_text = capsys.readouterr().out
    for model_name in MODEL_REGISTRY:
        assert model_name in help_text


def test_model_help_shows_model_specific_options(capsys):
    """Model subcommand --help lists model-specific and common options.

    Why: Verifies per-model help includes its unique flags and still shows the
    common flags like -p, keeping UX consistent and discoverable.
    """
    parser = build_parser(MODEL_REGISTRY)
    with pytest.raises(SystemExit):
        parser.parse_args(["dev", "--help"])
    help_text = capsys.readouterr().out
    assert "--num-inference-steps" in help_text
    assert "--guidance-scale" in help_text
    # common flags should also appear
    assert "-p" in help_text


def test_model_specific_option_parsing():
    """Parses and types model-specific options correctly.

    Why: Some options exist only for certain models and have types (int/float).
    The parser must coerce values and inject them into params with correct types.
    """
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(
        [
            "dev",
            "-p",
            "hi",
            "--num-inference-steps",
            "8",
            "--guidance-scale",
            "4.0",
        ],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert ns.params["num_inference_steps"] == 8
    assert ns.params["guidance_scale"] == pytest.approx(4.0)


def test_seed_default_is_random(monkeypatch):
    """Defaults seed to a random value but respects explicit -s overrides.

    Why: Reproducibility requires fixed seeds when provided, but users should get
    varied results by default; thus the parser must supply a random seed when
    none is specified and accept a user-provided value when present.
    """
    parser = build_parser(MODEL_REGISTRY)
    sentinel = 123456789
    monkeypatch.setattr("imagegen.options.secrets.randbits", lambda bits: sentinel)
    ns = parse_args(["schnell", "-p", "hello"], registry=MODEL_REGISTRY, parser=parser)
    assert ns.params["seed"] == sentinel
    ns_with_value = parse_args(
        ["schnell", "-p", "hello", "-s", "99"], registry=MODEL_REGISTRY, parser=parser
    )
    assert ns_with_value.params["seed"] == 99
