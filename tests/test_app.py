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


def test_buying_a_bar_from_the_phone(monkeypatch):
    monkeypatch.setattr(server.game.rng, "randint", lambda low, high: 4)
    host = connect()
    phone = connect()
    token = phone.emit("join", {"name": "Anna"}, callback=True)["token"]
    host.emit("start", callback=True)
    phone.emit("roll", {"token": token}, callback=True)
    assert last_state(host)["pending"]["type"] == "buy"

    assert phone.emit("buy", {"token": token}, callback=True)["ok"]

    state = last_state(host)
    assert state["owners"] == {"4": state["players"][0]["id"]}
    assert state["players"][0]["sips"] == 2
    assert state["pending"] is None


def test_giving_sips_from_the_phone(monkeypatch):
    monkeypatch.setattr(server.game.rng, "randint", lambda low, high: 3)
    anna_phone = connect()
    bo_phone = connect()
    anna = anna_phone.emit("join", {"name": "Anna"}, callback=True)
    bo = bo_phone.emit("join", {"name": "Bo"}, callback=True)
    anna_phone.emit("start", callback=True)
    server.game.players[0].position = 22
    anna_phone.emit("roll", {"token": anna["token"]}, callback=True)
    assert last_state(bo_phone)["pending"]["type"] == "give"

    result = anna_phone.emit("give", {"token": anna["token"], "target": bo["id"]}, callback=True)

    assert result["ok"]
    assert last_state(bo_phone)["players"][1]["sips"] == 2


def test_chance_card_reaches_every_screen(monkeypatch):
    monkeypatch.setattr(server, "game", Game(server.board, server.cards))
    monkeypatch.setattr(server.game.rng, "randint", lambda low, high: 3)
    host = connect()
    phone = connect()
    token = phone.emit("join", {"name": "Anna"}, callback=True)["token"]
    host.emit("start", callback=True)

    phone.emit("roll", {"token": token}, callback=True)

    pending = last_state(host)["pending"]
    assert pending["type"] == "card"
    assert pending["text"] in [card["text"] for card in server.cards]
    assert phone.emit("finish_card", {"token": token}, callback=True)["ok"]
    assert last_state(host)["pending"] is None


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
