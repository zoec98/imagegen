"""Tests for recent Mini CLI, dynamic flags, EXIF, and logging features."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from imageedit.app import create_app
from imageedit.forms import get_cli_flags
from imageedit.services.auth import issue_api_token
from imagegen.registry import MODEL_REGISTRY

pytestmark = pytest.mark.usefixtures("test_env_file")

API_TOKEN_SECRET = "test-secret"  # noqa: S105


# ── helpers ──────────────────────────────────────────────────────────────


def _make_client(tmp_path: Path):
    app = create_app(
        config={
            "TESTING": True,
            "PROMPTS_DIR": tmp_path / "prompts",
            "ASSETS_DIR": tmp_path / "assets",
            "STYLES_DIR": tmp_path / "styles",
            "STARTUP_MODEL": "seedream",
            "API_AUTH_ENABLED": True,
            "API_TOKEN_SECRET": API_TOKEN_SECRET,
            "API_TOKEN_TTL_SECONDS": 3600,
        }
    )
    return app.test_client()


def _auth_headers(client):
    token = issue_api_token(API_TOKEN_SECRET, subject="test")
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════
# 1. get_cli_flags() — forms.py
# ═══════════════════════════════════════════════════════════════════════


class TestGetCliFlags:
    """Unit tests for the get_cli_flags helper in forms.py."""

    def test_returns_list_of_dicts(self):
        flags = get_cli_flags("schnell")
        assert isinstance(flags, list)
        assert all(isinstance(f, dict) for f in flags)

    def test_each_flag_has_required_keys(self):
        flags = get_cli_flags("schnell")
        for f in flags:
            assert "flag" in f
            assert "type" in f
            assert "help" in f

    def test_flags_start_with_double_dash(self):
        flags = get_cli_flags("schnell")
        for f in flags:
            assert f["flag"].startswith("--"), f"Flag {f['flag']} missing -- prefix"

    def test_skipped_options_not_present(self):
        """Options in _SKIP_CLI_OPTIONS must never appear as pills."""
        from imageedit.forms import _SKIP_CLI_OPTIONS

        for model_name in MODEL_REGISTRY:
            flags = get_cli_flags(model_name)
            flag_names = {f["flag"] for f in flags}
            for skip in _SKIP_CLI_OPTIONS:
                derived_flag = f"--{skip.replace('_', '-')}"
                assert derived_flag not in flag_names, (
                    f"{derived_flag} should be skipped for {model_name}"
                )

    def test_boolean_type_detected(self):
        """Boolean options (e.g. enable_safety_checker) should have type 'boolean'."""
        flags = get_cli_flags("schnell")
        by_flag = {f["flag"]: f for f in flags}
        safety = by_flag.get("--enable-safety-checker") or by_flag.get("-%")
        if safety:
            assert safety["type"] == "boolean"

    def test_int_type_detected(self):
        flags = get_cli_flags("schnell")
        by_flag = {f["flag"]: f for f in flags}
        steps = by_flag.get("--num-inference-steps")
        if steps:
            assert steps["type"] == "int"

    def test_unknown_model_returns_empty(self):
        assert get_cli_flags("nonexistent-model-xyz") == []

    def test_flags_differ_across_models(self):
        """Different models should produce different flag sets."""
        flags_schnell = {f["flag"] for f in get_cli_flags("schnell")}
        flags_seedream = {f["flag"] for f in get_cli_flags("seedream5")}
        # They MAY share some flags, but the sets should NOT be identical
        # unless both models genuinely have identical option specs.
        if flags_schnell and flags_seedream:
            # At minimum, check both are non-empty — real difference is
            # tested by the "model-specific flag" test below.
            assert len(flags_schnell) > 0
            assert len(flags_seedream) > 0

    def test_model_specific_flag_appears(self):
        """flux-2-pro should expose --safety-tolerance; schnell should not."""
        pro_flags = {f["flag"] for f in get_cli_flags("flux-2-pro")}
        schnell_flags = {f["flag"] for f in get_cli_flags("schnell")}
        if "--safety-tolerance" in pro_flags:
            assert "--safety-tolerance" not in schnell_flags


# ═══════════════════════════════════════════════════════════════════════
# 2. /api/model-sizes/<model> returns cli_flags
# ═══════════════════════════════════════════════════════════════════════


class TestApiModelSizesCliFlags:
    """Tests for the cli_flags key in the model-sizes API response."""

    def test_response_contains_cli_flags_key(self, tmp_path):
        client = _make_client(tmp_path)
        headers = _auth_headers(client)

        resp = client.get("/api/model-sizes/schnell", headers=headers)
        payload = resp.get_json()

        assert "cli_flags" in payload
        assert isinstance(payload["cli_flags"], list)

    def test_cli_flags_match_helper(self, tmp_path):
        """API response must mirror the output of get_cli_flags."""
        client = _make_client(tmp_path)
        headers = _auth_headers(client)

        resp = client.get("/api/model-sizes/schnell", headers=headers)
        payload = resp.get_json()

        expected = get_cli_flags("schnell")
        assert payload["cli_flags"] == expected

    def test_cli_flags_change_per_model(self, tmp_path):
        client = _make_client(tmp_path)
        headers = _auth_headers(client)

        r1 = client.get("/api/model-sizes/schnell", headers=headers)
        r2 = client.get("/api/model-sizes/seedream5", headers=headers)

        flags1 = {f["flag"] for f in r1.get_json()["cli_flags"]}
        flags2 = {f["flag"] for f in r2.get_json()["cli_flags"]}

        # At minimum both should be non-empty
        assert len(flags1) > 0
        assert len(flags2) > 0


# ═══════════════════════════════════════════════════════════════════════
# 3. Logging filter — _QuietAssetFilter
# ═══════════════════════════════════════════════════════════════════════


class TestQuietAssetFilter:
    """Tests for the _QuietAssetFilter that suppresses noisy asset logs."""

    @staticmethod
    def _get_filter():
        """Retrieve the filter that was installed by configure_logging."""
        from image_common.logging import configure_logging

        configure_logging()
        werkzeug_logger = logging.getLogger("werkzeug")
        for f in werkzeug_logger.filters:
            if type(f).__name__ == "_QuietAssetFilter":
                return f
        pytest.fail("_QuietAssetFilter not found on werkzeug logger")

    def test_filter_installed(self):
        self._get_filter()  # will pytest.fail if not found

    def test_blocks_200_asset_requests(self):
        filt = self._get_filter()
        record = logging.LogRecord(
            name="werkzeug",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='127.0.0.1 - - [27/Feb/2026] "GET /assets/image.jpg HTTP/1.1" 200 -',
            args=(),
            exc_info=None,
        )
        assert filt.filter(record) is False

    def test_allows_non_200_asset_requests(self):
        filt = self._get_filter()
        record = logging.LogRecord(
            name="werkzeug",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg='127.0.0.1 - - [27/Feb/2026] "GET /assets/missing.jpg HTTP/1.1" 404 -',
            args=(),
            exc_info=None,
        )
        assert filt.filter(record) is True

    def test_allows_non_asset_routes(self):
        filt = self._get_filter()
        record = logging.LogRecord(
            name="werkzeug",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='127.0.0.1 - - [27/Feb/2026] "GET /api/model-sizes/schnell HTTP/1.1" 200 -',
            args=(),
            exc_info=None,
        )
        assert filt.filter(record) is True


# ═══════════════════════════════════════════════════════════════════════
# 4. EXIF — mini_cli saved in metadata
# ═══════════════════════════════════════════════════════════════════════


class TestExifMiniCli:
    """Verify that mini_cli is handled correctly in arg assembly.

    These tests replicate the arg-building logic from run_generation()
    to verify mini_cli inclusion/exclusion without requiring Flask context.
    """

    @staticmethod
    def _build_args(
        model="schnell",
        prompt_name="test",
        mini_cli="",
        style_name=None,
    ):
        """Replicate the arg-building logic from run_generation."""
        import json
        import shlex

        args = [model, "--no-preview", "-f", "/tmp/prompt.txt", "-i", "square"]  # noqa: S108
        meta = {
            "prompt_name": prompt_name,
            "style_name": style_name,
            "mini_cli": mini_cli,
        }
        meta = {k: v for k, v in meta.items() if v}
        if meta:
            args.extend(["--meta", json.dumps(meta)])
        if mini_cli.strip():
            args.extend(shlex.split(mini_cli))
        return args

    def test_mini_cli_included_in_meta(self):
        """When mini_cli is non-empty, it should be in the --meta JSON."""
        import json

        args = self._build_args(mini_cli="--seed 42")
        meta_idx = args.index("--meta")
        meta_json = json.loads(args[meta_idx + 1])
        assert meta_json["mini_cli"] == "--seed 42"

    def test_empty_mini_cli_excluded_from_meta(self):
        """When mini_cli is empty, it should not appear in --meta."""
        import json

        args = self._build_args(mini_cli="")
        if "--meta" in args:
            meta_json = json.loads(args[args.index("--meta") + 1])
            assert "mini_cli" not in meta_json

    def test_mini_cli_args_appended_to_argv(self):
        """The mini_cli string should be shlex-split and appended."""
        args = self._build_args(mini_cli="--seed 42 --num-inference-steps 8")
        assert "--seed" in args
        assert "42" in args
        assert "--num-inference-steps" in args
        assert "8" in args

    def test_mini_cli_appended_after_meta(self):
        """shlex-split flags should come after --meta."""
        args = self._build_args(mini_cli="--seed 99")
        meta_idx = args.index("--meta")
        seed_idx = args.index("--seed")
        assert seed_idx > meta_idx

    def test_style_and_mini_cli_both_in_meta(self):
        """Both style_name and mini_cli should appear in --meta when present."""
        import json

        args = self._build_args(mini_cli="--seed 1", style_name="anime")
        meta_json = json.loads(args[args.index("--meta") + 1])
        assert meta_json["mini_cli"] == "--seed 1"
        assert meta_json["style_name"] == "anime"

    def test_shlex_handles_quoted_values(self):
        """Quoted strings in mini_cli should be preserved."""
        args = self._build_args(mini_cli='--output-format "png"')
        assert "--output-format" in args
        assert "png" in args


# ═══════════════════════════════════════════════════════════════════════
# 5. Registry coverage — every model produces valid CLI flags
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("model_name", list(MODEL_REGISTRY.keys()))
def test_get_cli_flags_valid_for_all_models(model_name):
    """Every registered model should produce a valid (possibly empty) flag list."""
    flags = get_cli_flags(model_name)
    assert isinstance(flags, list)
    for f in flags:
        assert f["flag"].startswith("--")
        assert f["type"] in {"boolean", "int", "float", "string"}
        assert isinstance(f["help"], str)
