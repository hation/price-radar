from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import settings


def _build_settings_client() -> TestClient:
    app = FastAPI()
    app.include_router(settings.router)
    return TestClient(app)


def test_global_blacklist_get_and_put_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = _build_settings_client()

    resp = client.get("/api/settings/global-blacklist")
    assert resp.status_code == 200
    assert resp.json() == {"keywords": []}

    resp = client.put(
        "/api/settings/global-blacklist",
        json={"keywords": ["假货", "翻新机", ""]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keywords"] == ["假货", "翻新机"]

    resp = client.get("/api/settings/global-blacklist")
    assert resp.status_code == 200
    assert resp.json() == {"keywords": ["假货", "翻新机"]}
