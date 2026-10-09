import pytest

import app as server
from game.state import Game


@pytest.fixture(autouse=True)
def fresh_game(monkeypatch):
    monkeypatch.setattr(server, "game", Game(server.board))
    monkeypatch.setattr(server, "connections", {})


def connect():
    return server.socketio.test_client(server.app)


def last_state(client):
    states = [m["args"][0] for m in client.get_received() if m["name"] == "state"]
    return states[-1]


def test_pages_and_qr_code_load():
    http = server.app.test_client()
    assert http.get("/").status_code == 200
    assert http.get("/play").status_code == 200
    qr = http.get("/qr.svg")
    assert qr.status_code == 200
    assert qr.mimetype == "image/svg+xml"


def test_join_start_and_roll_updates_every_screen():
    host = connect()
    phone = connect()

    joined = phone.emit("join", {"name": "Anna"}, callback=True)
    assert joined["ok"]
    assert host.emit("start", callback=True)["ok"]
    assert phone.emit("roll", {"token": joined["token"]}, callback=True)["ok"]

    state = last_state(host)
    assert state["started"] is True
    assert state["players"][0]["name"] == "Anna"
    assert state["players"][0]["position"] == state["last_roll"]["to"] > 0


def test_join_with_taken_name_is_refused():
    connect().emit("join", {"name": "Anna"}, callback=True)
    result = connect().emit("join", {"name": "Anna"}, callback=True)
    assert result["ok"] is False
    assert result["error"]


def test_roll_with_wrong_token_is_refused():
    phone = connect()
    phone.emit("join", {"name": "Anna"}, callback=True)
    phone.emit("start", callback=True)
    assert phone.emit("roll", {"token": "forkert"}, callback=True)["ok"] is False


def test_phone_can_rejoin_after_losing_connection():
    host = connect()
    phone = connect()
    joined = phone.emit("join", {"name": "Anna"}, callback=True)

    phone.disconnect()
    assert last_state(host)["players"][0]["connected"] is False

    phone = connect()
    rejoined = phone.emit("rejoin", {"token": joined["token"]}, callback=True)
    assert rejoined == {"ok": True, "id": joined["id"]}
    assert last_state(host)["players"][0]["connected"] is True


def test_rejoin_with_unknown_token_is_refused():
    assert connect().emit("rejoin", {"token": "forkert"}, callback=True) == {"ok": False}
