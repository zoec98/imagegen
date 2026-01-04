import importlib
from io import BytesIO
import sys
import types
from email.message import Message

import pytest
from PIL import Image

from imagegen.options import ParsedOptions


class _FakeResponse:
    def __init__(self, data: bytes, content_type: str):
        self._data = data
        self._content_type = content_type

    def read(self) -> bytes:
        return self._data

    def info(self) -> Message:
        message = Message()
        message.add_header("Content-Type", self._content_type)
        return message

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.fixture()
def reload_imagegen(monkeypatch):
    def _loader(fal_module: types.SimpleNamespace):
        monkeypatch.setitem(sys.modules, "fal_client", fal_module)
        sys.modules.pop("imagegen.imagegen", None)
        return importlib.import_module("imagegen.imagegen")

    return _loader


def test_generate_images_run_invocation(monkeypatch, tmp_path, reload_imagegen):
    # REVIEW: 2026-01-04 editor upgrade
    captured = {}

    def run(endpoint, *, arguments):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {
            "request_id": "run-req-123",
            "images": [
                {"url": "https://example.com/image-1.png"},
                {"url": "https://example.com/image-2.jpeg"},
            ],
        }

    fal_module = types.SimpleNamespace(run=run, subscribe=lambda *args, **kwargs: None)
    mod = reload_imagegen(fal_module)

    emitted = []
    monkeypatch.setattr(
        mod,
        "_emit_request_info",
        lambda endpoint, call, args: emitted.append((endpoint, call, dict(args))),
    )
    elapsed = []
    monkeypatch.setattr(mod, "_emit_elapsed", lambda seconds: elapsed.append(seconds))
    opened = []
    monkeypatch.setattr(mod, "_handle_post_write", lambda path: opened.append(path))
    exif_calls = []
    monkeypatch.setattr(
        mod.exif,
        "set_exif_data",
        lambda path, **kwargs: exif_calls.append((path, kwargs)) or True,
    )

    perf_values = iter([100.0, 101.5])
    monkeypatch.setattr(mod.time, "perf_counter", lambda: next(perf_values))
    monkeypatch.setattr(mod.time, "strftime", lambda *_args, **_kwargs: "20260104_114516")

    responses = iter(
        [
            _FakeResponse(b"img1", "image/png"),
            _FakeResponse(b"img2", "image/jpeg"),
        ]
    )

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda url: next(responses))

    parsed = ParsedOptions(
        model="schnell",
        endpoint="fal-ai/flux/schnell",
        call="run",
        params={
            "prompt": "hello",
            "file": "prompts/cats.txt",
        },
        as_jpg=False,
    )

    output = mod.generate_images(parsed, output_dir=tmp_path)

    assert captured["endpoint"] == "fal-ai/flux/schnell"
    assert captured["arguments"]["prompt"] == "hello"
    assert len(output) == 2

    expected_1 = tmp_path / "cats-hello-20260104_114516.png"
    expected_2 = tmp_path / "cats-hello-20260104_114516.jpg"

    assert output == [expected_1, expected_2]
    assert expected_1.read_bytes() == b"img1"
    assert expected_2.read_bytes() == b"img2"
    assert opened == [expected_1, expected_2]
    assert emitted == [
        (
            "fal-ai/flux/schnell",
            "run",
            {"prompt": "hello", "file": "prompts/cats.txt"},
        )
    ]
    assert elapsed == [pytest.approx(1.5)]
    assert exif_calls == [
        (expected_1, {"description": None, "model": parsed.model}),
        (expected_2, {"description": None, "model": parsed.model}),
    ]


def test_generate_images_subscribe(monkeypatch, tmp_path, reload_imagegen):
    # REVIEW: 2026-01-04 editor upgrade
    class Subscription:
        def __init__(self):
            self.request_id = "sub-req-789"

        def get(self):
            return {"output": [{"url": "https://example.com/sub.png"}]}

    captured = {}

    def subscribe(endpoint, *, arguments, with_logs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        captured["with_logs"] = with_logs
        return Subscription()

    fal_module = types.SimpleNamespace(
        run=lambda *args, **kwargs: None, subscribe=subscribe
    )
    mod = reload_imagegen(fal_module)

    emitted = []
    monkeypatch.setattr(
        mod,
        "_emit_request_info",
        lambda endpoint, call, args: emitted.append((endpoint, call, dict(args))),
    )
    elapsed = []
    monkeypatch.setattr(mod, "_emit_elapsed", lambda seconds: elapsed.append(seconds))
    opened = []
    monkeypatch.setattr(mod, "_handle_post_write", lambda path: opened.append(path))
    exif_calls = []
    monkeypatch.setattr(
        mod.exif,
        "set_exif_data",
        lambda path, **kwargs: exif_calls.append((path, kwargs)) or True,
    )

    perf_values = iter([200.0, 205.25])
    monkeypatch.setattr(mod.time, "perf_counter", lambda: next(perf_values))
    monkeypatch.setattr(mod.time, "strftime", lambda *_args, **_kwargs: "20260104_114516")

    monkeypatch.setattr(
        mod.urllib.request,
        "urlopen",
        lambda url: _FakeResponse(b"sub", "image/png"),
    )

    parsed = ParsedOptions(
        model="dev",
        endpoint="fal-ai/flux/dev",
        call="subscribe",
        params={
            "prompt": "hi",
        },
        as_jpg=False,
    )

    output = mod.generate_images(parsed, output_dir=tmp_path)

    expected = tmp_path / "hi-20260104_114516.png"
    assert output == [expected]
    assert expected.read_bytes() == b"sub"
    assert captured["endpoint"] == "fal-ai/flux/dev"
    assert captured["arguments"]["prompt"] == "hi"
    assert captured["with_logs"] is False
    assert opened == [expected]
    assert exif_calls == [
        (expected, {"description": None, "model": parsed.model}),
    ]
    assert emitted == [
        (
            "fal-ai/flux/dev",
            "subscribe",
            {"prompt": "hi"},
        )
    ]
    assert elapsed == [pytest.approx(5.25)]


def test_generate_images_adds_prompt_description_when_requested(
    monkeypatch, tmp_path, reload_imagegen
):
    # REVIEW: 2026-01-04 editor upgrade
    def run(endpoint, *, arguments):
        return {
            "request_id": "abc123",
            "images": [{"url": "https://example.com/only.png"}],
        }

    fal_module = types.SimpleNamespace(run=run, subscribe=lambda *args, **kwargs: None)
    mod = reload_imagegen(fal_module)

    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda url: _FakeResponse(b"x", "image/png")
    )
    monkeypatch.setattr(mod, "_handle_post_write", lambda path: None)
    monkeypatch.setattr(mod, "_emit_request_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_emit_elapsed", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod.time, "strftime", lambda *_args, **_kwargs: "20260104_114516")

    exif_calls = []
    monkeypatch.setattr(
        mod.exif,
        "set_exif_data",
        lambda path, **kwargs: exif_calls.append((path, kwargs)) or True,
    )

    parsed = ParsedOptions(
        model="schnell",
        endpoint="fal-ai/flux/schnell",
        call="run",
        params={"prompt": "  dreamy forest scene  "},
        add_prompt_metadata=True,
        as_jpg=False,
    )

    output = mod.generate_images(parsed, output_dir=tmp_path)

    expected = tmp_path / "dreamy-forest-scene-20260104_114516.png"
    assert output == [expected]
    assert exif_calls == [
        (
            expected,
            {"description": "dreamy forest scene", "model": parsed.model},
        ),
    ]


def test_generate_images_skips_preview_when_disabled(
    monkeypatch, tmp_path, reload_imagegen
):
    # REVIEW: 2026-01-04 editor upgrade
    def run(endpoint, *, arguments):
        return {
            "request_id": "skip-req",
            "images": [{"url": "https://example.com/img.png"}],
        }

    fal_module = types.SimpleNamespace(run=run, subscribe=lambda *args, **kwargs: None)
    mod = reload_imagegen(fal_module)

    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda url: _FakeResponse(b"x", "image/png")
    )
    opened = []
    monkeypatch.setattr(mod, "_handle_post_write", lambda path: opened.append(path))
    monkeypatch.setattr(mod, "_emit_request_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_emit_elapsed", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod.time, "strftime", lambda *_args, **_kwargs: "20260104_114516")
    monkeypatch.setattr(
        mod.exif,
        "set_exif_data",
        lambda path, **kwargs: True,
    )

    parsed = ParsedOptions(
        model="schnell",
        endpoint="fal-ai/flux/schnell",
        call="run",
        params={"prompt": "skip", "file": "prompts/skip.txt"},
        preview_assets=False,
        as_jpg=False,
    )

    output = mod.generate_images(parsed, output_dir=tmp_path)

    expected = tmp_path / "skip-skip-20260104_114516.png"
    assert output == [expected]
    assert opened == []


def test_generate_images_converts_png_to_jpg(monkeypatch, tmp_path, reload_imagegen):
    # REVIEW: 2026-01-04 editor upgrade
    def run(endpoint, *, arguments):
        return {
            "request_id": "conv-req",
            "images": [{"url": "https://example.com/img.png"}],
        }

    fal_module = types.SimpleNamespace(run=run, subscribe=lambda *args, **kwargs: None)
    mod = reload_imagegen(fal_module)

    buffer = BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda url: _FakeResponse(png_bytes, "image/png")
    )
    monkeypatch.setattr(mod, "_handle_post_write", lambda path: None)
    monkeypatch.setattr(mod, "_emit_request_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_emit_elapsed", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod.time, "strftime", lambda *_args, **_kwargs: "20260104_114516")
    monkeypatch.setattr(
        mod.exif,
        "set_exif_data",
        lambda path, **kwargs: True,
    )

    parsed = ParsedOptions(
        model="schnell",
        endpoint="fal-ai/flux/schnell",
        call="run",
        params={"prompt": "convert"},
        as_jpg=True,
        jpg_options={
            "quality": 75,
            "subsampling": 2,
            "progressive": True,
            "optimize": True,
        },
    )

    output = mod.generate_images(parsed, output_dir=tmp_path)

    expected = tmp_path / "convert-20260104_114516.jpg"
    assert output == [expected]
    assert expected.read_bytes()[:2] == b"\xff\xd8"
