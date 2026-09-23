import json
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import login_state


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(login_state.router)
    return TestClient(app)


def test_update_login_state_writes_valid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _build_client()
    payload = {"content": json.dumps({"cookies": []})}

    response = client.post("/api/login-state", json=payload)

    assert response.status_code == 200
    from src.infrastructure.config.settings import scraper_settings

    assert os.path.exists(scraper_settings.state_file)
    with open(scraper_settings.state_file, encoding="utf-8") as f:
        assert json.load(f) == {"cookies": []}


def test_update_login_state_rejects_invalid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _build_client()

    response = client.post("/api/login-state", json={"content": "not json"})

    assert response.status_code == 400


def test_delete_login_state_removes_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _build_client()
    client.post("/api/login-state", json={"content": "{}"})

    response = client.delete("/api/login-state")

    assert response.status_code == 200
    from src.infrastructure.config.settings import scraper_settings

    assert not os.path.exists(scraper_settings.state_file)


def test_delete_login_state_is_a_noop_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _build_client()

    response = client.delete("/api/login-state")

    assert response.status_code == 200
    assert "不存在" in response.json()["message"]
