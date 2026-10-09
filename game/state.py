"""Game rules and state. No Flask in here, so it can be tested on its own."""

import json
import random
import secrets
from dataclasses import dataclass
from pathlib import Path

PLAYER_COLORS = [
    "#ff3b6b",
    "#22d3ee",
    "#facc15",
    "#4ade80",
    "#c084fc",
    "#fb923c",
    "#f472b6",
    "#a3e635",
]
MAX_NAME_LENGTH = 14
FIELD_TYPES = {"start", "bar", "chance", "brandert"}


class GameError(Exception):
    """A rule was broken. The message is shown to the players, so it is in Danish."""


def sips_text(count):
    return "1 tår" if count == 1 else f"{count} tårer"


def load_board(path):
    board = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_board(board)
    return board


def validate_board(board):
    fields = board["fields"]
    if len(fields) < 8 or len(fields) % 4 != 0:
        raise ValueError("The board must have a number of fields divisible by 4 (e.g. 24)")
    if fields[0]["type"] != "start":
        raise ValueError("The first field must be the start field")
    for index, field in enumerate(fields):
        if field["type"] not in FIELD_TYPES:
            raise ValueError(f"Field {index} has unknown type {field['type']!r}")
        if field["type"] != "bar":
            continue
        if field["group"] not in board["groups"]:
            raise ValueError(f"Field {index} uses unknown group {field['group']!r}")
        for key in ("price", "sips"):
            if not isinstance(field.get(key), int) or field[key] < 0:
                raise ValueError(f"Field {index} needs a whole number for {key!r}")


@dataclass
class Player:
    id: int
    token: str  # secret, only known by the player's own phone
    name: str
    color: str
    position: int = 0
    sips: int = 0  # sips taken so far
    connected: bool = True

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "position": self.position,
            "sips": self.sips,
            "connected": self.connected,
        }


class Game:
    def __init__(self, board, dice_sides=6, max_players=8, rng=None):
        self.board = board
        self.dice_sides = dice_sides
        self.max_players = min(max_players, len(PLAYER_COLORS))
        self.rng = rng or random.Random()
        self.players = []
        self.started = False
        self.turn = 0
        self.last_roll = None
        self.owners = {}  # field index -> player id
        self.pending = None  # a choice the current player must make before the turn ends
        self.message = ""
        self._next_id = 1
        self._roll_seq = 0

    @property
    def current_player(self):
        if not self.started or not self.players:
            return None
        return self.players[self.turn]

    def find_by_token(self, token):
        for player in self.players:
            if player.token == token:
                return player
        return None

    def add_player(self, name):
        name = " ".join(str(name).split())[:MAX_NAME_LENGTH]
        if not name:
            raise GameError("Skriv et navn")
        if any(p.name.lower() == name.lower() for p in self.players):
            raise GameError("Det navn er allerede taget")
        if len(self.players) >= self.max_players:
            raise GameError("Spillet er fyldt op")
        used = {p.color for p in self.players}
        color = next(c for c in PLAYER_COLORS if c not in used)
        player = Player(self._next_id, secrets.token_urlsafe(16), name, color)
        self._next_id += 1
        self.players.append(player)
        return player

    def start(self):
        if self.started:
            raise GameError("Spillet er allerede i gang")
        if not self.players:
            raise GameError("Der er ingen spillere endnu")
        self.started = True
        self.turn = 0

    def roll(self, token):
        if not self.started:
            raise GameError("Spillet er ikke startet endnu")
        player = self.find_by_token(token)
        if player is None:
            raise GameError("Ukendt spiller")
        if player is not self.current_player:
            raise GameError("Det er ikke din tur")
        if self.pending:
            raise GameError("Vælg først, om du vil købe baren")
        value = self.rng.randint(1, self.dice_sides)
        size = len(self.board["fields"])
        start = player.position
        player.position = (start + value) % size
        self._roll_seq += 1
        self.last_roll = {
            "seq": self._roll_seq,
            "player_id": player.id,
            "value": value,
            "from": start,
            "to": player.position,
            "passed_start": start + value >= size,
            "field": self.board["fields"][player.position]["name"],
        }
        field = self.board["fields"][player.position]
        self.message = f"{player.name} slog {value} og landede på {field['name']}"
        if field["type"] == "bar" and player.position not in self.owners:
            self.pending = {
                "type": "buy",
                "player_id": player.id,
                "field": player.position,
                "price": field["price"],
            }
        else:
            self._next_turn()
        return self.last_roll

    def buy(self, token):
        player = self._pending_buyer(token)
        field = self.board["fields"][self.pending["field"]]
        self.owners[self.pending["field"]] = player.id
        player.sips += field["price"]
        self.message = f"{player.name} købte {field['name']} og drikker {sips_text(field['price'])}"
        self.pending = None
        self._next_turn()

    def decline(self, token):
        player = self._pending_buyer(token)
        field = self.board["fields"][self.pending["field"]]
        self.message = f"{player.name} købte ikke {field['name']}"
        self.pending = None
        self._next_turn()

    def skip_turn(self):
        if not self.started:
            raise GameError("Spillet er ikke startet endnu")
        self.pending = None
        self._next_turn()

    def reset(self):
        """Back to the lobby. The players stay, so nobody has to join again."""
        self.started = False
        self.turn = 0
        self.last_roll = None
        self.owners = {}
        self.pending = None
        self.message = ""
        for player in self.players:
            player.position = 0
            player.sips = 0

    def _pending_buyer(self, token):
        player = self.find_by_token(token)
        if player is None:
            raise GameError("Ukendt spiller")
        if not self.pending or self.pending["player_id"] != player.id:
            raise GameError("Du har ikke noget at købe lige nu")
        return player

    def _next_turn(self):
        self.turn = (self.turn + 1) % len(self.players)

    def to_dict(self):
        current = self.current_player
        return {
            "started": self.started,
            "players": [p.to_dict() for p in self.players],
            "current_player_id": current.id if current else None,
            "last_roll": self.last_roll,
            "owners": {str(index): owner for index, owner in self.owners.items()},
            "pending": self.pending,
            "message": self.message,
        }
