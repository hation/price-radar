from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import prompts


def _build_client(tmp_path, monkeypatch) -> TestClient:
    # prompts._PROMPTS_DIR is resolved once at import time from the CWD at that
    # moment, so monkeypatch.chdir() alone (used elsewhere in this test suite)
    # would not isolate it — the module-level constant itself must be patched.
    monkeypatch.setattr(prompts, "_PROMPTS_DIR", tmp_path.resolve())
    app = FastAPI()
    app.include_router(prompts.router)
    return TestClient(app)


def test_list_prompts_returns_only_txt_files(tmp_path, monkeypatch):
    (tmp_path / "base_prompt.txt").write_text("base", encoding="utf-8")
    (tmp_path / "criteria.txt").write_text("criteria", encoding="utf-8")
    (tmp_path / "notes.md").write_text("ignore me", encoding="utf-8")
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/api/prompts")

    assert response.status_code == 200
    assert sorted(response.json()) == ["base_prompt.txt", "criteria.txt"]


def test_list_prompts_returns_empty_list_when_dir_missing(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does-not-exist"
    monkeypatch.setattr(prompts, "_PROMPTS_DIR", missing_dir)
    app = FastAPI()
    app.include_router(prompts.router)
    client = TestClient(app)

    response = client.get("/api/prompts")

    assert response.status_code == 200
    assert response.json() == []


def test_get_prompt_returns_content(tmp_path, monkeypatch):
    (tmp_path / "base_prompt.txt").write_text("hello world", encoding="utf-8")
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/api/prompts/base_prompt.txt")

    assert response.status_code == 200
    assert response.json() == {"filename": "base_prompt.txt", "content": "hello world"}


def test_get_prompt_404_when_missing(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/api/prompts/missing.txt")

    assert response.status_code == 404


def test_update_prompt_writes_new_content(tmp_path, monkeypatch):
    (tmp_path / "base_prompt.txt").write_text("old", encoding="utf-8")
    client = _build_client(tmp_path, monkeypatch)

    response = client.put("/api/prompts/base_prompt.txt", json={"content": "new"})

    assert response.status_code == 200
    assert (tmp_path / "base_prompt.txt").read_text(encoding="utf-8") == "new"


def test_get_prompt_rejects_path_traversal(tmp_path, monkeypatch):
    outside_file = tmp_path.parent / "secret.txt"
    outside_file.write_text("top secret", encoding="utf-8")
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/api/prompts/..%2Fsecret.txt")

    assert response.status_code in (400, 404)
    assert "top secret" not in response.text
