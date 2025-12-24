from __future__ import annotations

from pathlib import Path

from imageedit.app import _next_copy_name, create_app


def _make_client(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    assets_dir = tmp_path / "assets"
    app = create_app(
        config={
            "TESTING": True,
            "PROMPTS_DIR": prompts_dir,
            "ASSETS_DIR": assets_dir,
        }
    )
    return app.test_client(), prompts_dir, assets_dir


def test_lists_existing_prompts(tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "alpha.txt").write_text("hello", encoding="utf-8")

    response = client.get("/")
    body = response.get_data(as_text=True)

    assert "alpha" in body


def test_save_creates_or_updates_prompt(tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)

    response = client.post(
        "/",
        data={"prompt_name": "new_prompt", "prompt_text": "content", "action": "save"},
    )

    saved_path = prompts_dir / "new_prompt.txt"
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == "content"
    assert "Saved prompt" in response.get_data(as_text=True)


def test_save_normalizes_newlines(tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)

    client.post(
        "/",
        data={
            "prompt_name": "win",
            "prompt_text": "line1\r\nline2\rline3\nline4",
            "action": "save",
        },
    )

    saved_path = prompts_dir / "win.txt"
    assert saved_path.read_text(encoding="utf-8") == "line1\nline2\nline3\nline4"


def test_load_reads_existing_prompt(tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "beta.txt").write_text("beta content", encoding="utf-8")

    response = client.post("/", data={"prompt_name": "beta", "action": "load"})

    body = response.get_data(as_text=True)
    assert "beta content" in body
    assert "Loaded prompt" in body


def test_delete_removes_prompt(tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    target = prompts_dir / "gamma.txt"
    target.write_text("gamma", encoding="utf-8")

    response = client.post("/", data={"prompt_name": "gamma", "action": "delete"})

    assert not target.exists()
    assert "Deleted prompt" in response.get_data(as_text=True)


def test_run_generates_images(monkeypatch, tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_dir / "delta.txt"
    prompt_path.write_text("delta text", encoding="utf-8")

    captured = {}

    def fake_generate(parsed):
        captured["parsed"] = parsed
        return [Path("assets/delta-1.png")]

    monkeypatch.setattr("imageedit.app.generate_images", fake_generate)

    response = client.post(
        "/",
        data={
            "prompt_name": "delta",
            "prompt_text": "delta text new",
            "model_name": "schnell",
            "image_size": "square",
            "include_prompt_metadata": "on",
            "action": "run",
        },
    )

    body = response.get_data(as_text=True)
    assert "Generated 1 image" in body
    assert "assets/delta-1.png" in body
    parsed = captured["parsed"]
    assert parsed.model == "schnell"
    assert parsed.add_prompt_metadata is True
    assert parsed.params["image_size"] == "square"
    assert parsed.preview_assets is False


def test_run_with_image_urls(monkeypatch, tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_dir / "edit.txt"
    prompt_path.write_text("edit text", encoding="utf-8")

    captured = {}

    def fake_generate(parsed):
        captured["parsed"] = parsed
        return [Path("assets/edit-1.png")]

    monkeypatch.setattr("imageedit.app.generate_images", fake_generate)

    response = client.post(
        "/",
        data={
            "prompt_name": "edit",
            "prompt_text": "new text",
            "model_name": "qwen-image-edit",
            "image_size": "portrait_4_3",
            "image_urls": "https://example.com/a.jpg\nhttps://example.com/b.png",
            "action": "run",
        },
    )

    assert "Generated 1 image" in response.get_data(as_text=True)
    parsed = captured["parsed"]
    assert parsed.model == "qwen-image-edit"
    assert parsed.params["image_urls"] == [
        "https://example.com/a.jpg",
        "https://example.com/b.png",
    ]
    assert parsed.preview_assets is False


def test_asset_route_serves_files(tmp_path):
    client, _, assets_dir = _make_client(tmp_path)
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / "test.txt"
    target.write_text("hello, world", encoding="utf-8")

    response = client.get("/assets/test.txt")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "hello, world"


def test_next_copy_name_increments_suffixes():
    assert _next_copy_name("truc") == "truc_copy"
    assert _next_copy_name("truc_copy") == "truc_copy2"
    assert _next_copy_name("truc_copy2") == "truc_copy3"
    assert _next_copy_name("truc_copy999") == "truc_copy1000"
