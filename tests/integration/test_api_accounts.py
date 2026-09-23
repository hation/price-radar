import json
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import accounts


def _build_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ACCOUNT_STATE_DIR", raising=False)
    app = FastAPI()
    app.include_router(accounts.router)
    return TestClient(app)


def test_list_accounts_empty_when_state_dir_missing(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/api/accounts")

    assert response.status_code == 200
    assert response.json() == []


def test_create_account_then_list_and_get(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    payload = {"name": "account_one", "content": json.dumps({"cookies": []})}

    create_resp = client.post("/api/accounts", json=payload)
    assert create_resp.status_code == 200
    assert os.path.exists(tmp_path / "state" / "account_one.json")

    list_resp = client.get("/api/accounts")
    assert [a["name"] for a in list_resp.json()] == ["account_one"]

    get_resp = client.get("/api/accounts/account_one")
    assert get_resp.status_code == 200
    assert json.loads(get_resp.json()["content"]) == {"cookies": []}


def test_create_account_rejects_invalid_name(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/accounts", json={"name": "../evil", "content": "{}"}
    )

    assert response.status_code == 400


def test_create_account_rejects_invalid_json_content(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/accounts", json={"name": "account_one", "content": "not json"}
    )

    assert response.status_code == 400


def test_create_account_conflicts_when_already_exists(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    payload = {"name": "account_one", "content": "{}"}
    client.post("/api/accounts", json=payload)

    response = client.post("/api/accounts", json=payload)

    assert response.status_code == 409


def test_update_account_requires_existing_account(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.put("/api/accounts/account_one", json={"content": "{}"})

    assert response.status_code == 404


def test_update_account_overwrites_content(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    client.post("/api/accounts", json={"name": "account_one", "content": "{}"})

    response = client.put(
        "/api/accounts/account_one", json={"content": json.dumps({"updated": True})}
    )

    assert response.status_code == 200
    assert json.loads((tmp_path / "state" / "account_one.json").read_text(encoding="utf-8")) == {
        "updated": True
    }


def test_delete_account_removes_file(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    client.post("/api/accounts", json={"name": "account_one", "content": "{}"})

    response = client.delete("/api/accounts/account_one")

    assert response.status_code == 200
    assert not os.path.exists(tmp_path / "state" / "account_one.json")


def test_delete_account_404_when_missing(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.delete("/api/accounts/account_one")

    assert response.status_code == 404
