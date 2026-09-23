import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import websocket


@pytest.fixture(autouse=True)
def _clear_active_connections():
    websocket.active_connections.clear()
    yield
    websocket.active_connections.clear()


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(websocket.router)
    return TestClient(app)


def test_websocket_connect_registers_and_disconnect_unregisters():
    client = _build_client()

    with client.websocket_connect("/ws") as ws:
        assert len(websocket.active_connections) == 1

    assert len(websocket.active_connections) == 0


def test_broadcast_message_delivers_to_connected_client():
    client = _build_client()

    with client.websocket_connect("/ws") as ws:
        asyncio.run(websocket.broadcast_message("tasks_updated", {"task_id": 1}))
        received = ws.receive_json()

    assert received == {"type": "tasks_updated", "data": {"task_id": 1}}


def test_broadcast_message_drops_dead_connections_without_raising():
    class _DeadConnection:
        async def send_json(self, message):
            raise RuntimeError("connection closed")

    dead = _DeadConnection()
    websocket.active_connections.add(dead)

    asyncio.run(websocket.broadcast_message("ping", {}))

    assert dead not in websocket.active_connections
