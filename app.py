"""Tour de Bytur: web server for the shared host screen and the players' phones."""

import json
import socket
import threading
from io import BytesIO
from pathlib import Path

import qrcode
import qrcode.image.svg
from flask import Flask, Response, render_template, request
from flask_socketio import SocketIO

from game.state import Game, GameError, load_board

DATA_DIR = Path(__file__).parent / "data"
PORT = 5001  # macOS uses port 5000 for AirPlay

app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")

board = load_board(DATA_DIR / "board.json")
settings = json.loads((DATA_DIR / "settings.json").read_text(encoding="utf-8"))
game = Game(board, dice_sides=settings["dice_sides"], max_players=settings["max_players"])
lock = threading.Lock()
connections = {}  # socket id -> player token


def local_ip():
    """The Mac's address on the wifi, so phones can reach the server."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # no data is sent
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def join_url():
    return f"http://{local_ip()}:{PORT}/play"


def broadcast_state():
    socketio.emit("state", game.to_dict())


def update_connected(player):
    player.connected = player.token in connections.values()


@app.route("/")
def host():
    return render_template("host.html", board=board, join_url=join_url())


@app.route("/play")
def play():
    return render_template("player.html")


@app.route("/qr.svg")
def qr_code():
    image = qrcode.make(join_url(), image_factory=qrcode.image.svg.SvgPathImage, border=2)
    buffer = BytesIO()
    image.save(buffer)
    return Response(buffer.getvalue(), mimetype="image/svg+xml")


@socketio.on("connect")
def on_connect():
    socketio.emit("state", game.to_dict(), to=request.sid)


@socketio.on("disconnect")
def on_disconnect():
    with lock:
        token = connections.pop(request.sid, None)
        player = game.find_by_token(token)
        if player is None:
            return
        update_connected(player)
    broadcast_state()


@socketio.on("join")
def on_join(data):
    with lock:
        try:
            player = game.add_player((data or {}).get("name", ""))
        except GameError as error:
            return {"ok": False, "error": str(error)}
        connections[request.sid] = player.token
    broadcast_state()
    return {"ok": True, "id": player.id, "token": player.token}


@socketio.on("rejoin")
def on_rejoin(data):
    """A phone that reloaded the page or woke up gets its player back."""
    with lock:
        player = game.find_by_token((data or {}).get("token"))
        if player is None:
            return {"ok": False}
        connections[request.sid] = player.token
        update_connected(player)
    broadcast_state()
    return {"ok": True, "id": player.id}


def run_action(action, *args):
    with lock:
        try:
            action(*args)
        except GameError as error:
            return {"ok": False, "error": str(error)}
    broadcast_state()
    return {"ok": True}


@socketio.on("roll")
def on_roll(data):
    return run_action(game.roll, (data or {}).get("token"))


@socketio.on("buy")
def on_buy(data):
    return run_action(game.buy, (data or {}).get("token"))


@socketio.on("decline")
def on_decline(data):
    return run_action(game.decline, (data or {}).get("token"))


@socketio.on("start")
def on_start():
    return run_action(game.start)


@socketio.on("skip")
def on_skip():
    return run_action(game.skip_turn)


@socketio.on("reset")
def on_reset():
    return run_action(game.reset)


if __name__ == "__main__":
    print(f"\n  Værtsskærm:  http://localhost:{PORT}")
    print(f"  Telefoner:   {join_url()}\n")
    socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)
