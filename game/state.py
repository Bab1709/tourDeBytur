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


def load_cards(path):
    cards = json.loads(Path(path).read_text(encoding="utf-8"))["cards"]
    for index, card in enumerate(cards):
        if not isinstance(card.get("text"), str) or not card["text"].strip():
            raise ValueError(f"Chance card {index} needs a text")
    return cards


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
    skip_next: bool = False
    connected: bool = True

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "position": self.position,
            "sips": self.sips,
            "skip_next": self.skip_next,
            "connected": self.connected,
        }


class Game:
    def __init__(
        self,
        board,
        cards=(),
        dice_sides=6,
        max_players=8,
        pass_start_sips=2,
        group_multiplier=2,
        rng=None,
    ):
        self.board = board
        self.cards = list(cards)
        self._deck = []  # shuffled cards not drawn yet
        self.dice_sides = dice_sides
        self.max_players = min(max_players, len(PLAYER_COLORS))
        self.pass_start_sips = pass_start_sips
        self.group_multiplier = group_multiplier
        self.rng = rng or random.Random()
        self.players = []
        self.started = False
        self.turn = 0
        self.last_roll = None
        self.owners = {}  # field index -> player id
        self.pending = None  # a choice the current player must make before the turn ends
        self._queue = []  # further choices waiting behind the pending one
        self._events = []  # what has happened in the current turn, shown on every screen
        self._next_id = 1
        self._roll_seq = 0

    @property
    def current_player(self):
        if not self.started or not self.players:
            return None
        return self.players[self.turn]

    @property
    def message(self):
        return "\n".join(self._events)

    def find_by_token(self, token):
        for player in self.players:
            if player.token == token:
                return player
        return None

    def find_by_id(self, player_id):
        for player in self.players:
            if player.id == player_id:
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
            raise GameError("Du skal vælge, før du kan rulle igen")
        value = self.rng.randint(1, self.dice_sides)
        size = len(self.board["fields"])
        start = player.position
        player.position = (start + value) % size
        field = self.board["fields"][player.position]
        self._roll_seq += 1
        self.last_roll = {
            "seq": self._roll_seq,
            "player_id": player.id,
            "value": value,
            "from": start,
            "to": player.position,
            "passed_start": start + value >= size,
            "field": field["name"],
        }
        self._events = [f"{player.name} slog {value} og landede på {field['name']}"]
        self._queue = []
        if self.last_roll["passed_start"] and self.pass_start_sips > 0 and len(self.players) > 1:
            self._queue.append(
                {"type": "give", "player_id": player.id, "sips": self.pass_start_sips}
            )
        self._land(player, field)
        self._advance()
        return self.last_roll

    def rent(self, index):
        """Sips for landing on an owned bar, multiplied if the owner has the whole group."""
        field = self.board["fields"][index]
        owner = self.owners[index]
        group = [
            i
            for i, other in enumerate(self.board["fields"])
            if other["type"] == "bar" and other["group"] == field["group"]
        ]
        if all(self.owners.get(i) == owner for i in group):
            return field["sips"] * self.group_multiplier
        return field["sips"]

    def buy(self, token):
        player = self._chooser(token, "buy")
        field = self.board["fields"][self.pending["field"]]
        self.owners[self.pending["field"]] = player.id
        player.sips += field["price"]
        self._events.append(
            f"{player.name} købte {field['name']} og drikker {sips_text(field['price'])}"
        )
        self._advance()

    def decline(self, token):
        player = self._chooser(token, "buy")
        field = self.board["fields"][self.pending["field"]]
        self._events.append(f"{player.name} købte ikke {field['name']}")
        self._advance()

    def give(self, token, target_id):
        """Hand out the sips earned by passing start to another player."""
        player = self._chooser(token, "give")
        target = self.find_by_id(target_id)
        if target is None or target is player:
            raise GameError("Vælg en anden spiller")
        target.sips += self.pending["sips"]
        self._events.append(
            f"{player.name} passerede start og gav {sips_text(self.pending['sips'])} til {target.name}"
        )
        self._advance()

    def finish_card(self, token):
        """The player has done what the chance card said."""
        self._chooser(token, "card")
        self._advance()

    def skip_turn(self):
        if not self.started:
            raise GameError("Spillet er ikke startet endnu")
        self._events = [f"{self.current_player.name}s tur blev sprunget over"]
        self._queue = []
        self._advance()

    def reset(self):
        """Back to the lobby. The players stay, so nobody has to join again."""
        self.started = False
        self.turn = 0
        self.last_roll = None
        self.owners = {}
        self.pending = None
        self._queue = []
        self._events = []
        self._deck = []
        for player in self.players:
            player.position = 0
            player.sips = 0
            player.skip_next = False

    def _land(self, player, field):
        if field["type"] == "brandert":
            player.skip_next = True
            self._events.append(
                f"{player.name} drikker et glas vand og springer næste tur over"
            )
        elif field["type"] == "chance" and self.cards:
            text = self._draw_card()
            self._events.append(f"{player.name} trak et chance-kort: {text}")
            self._queue.append({"type": "card", "player_id": player.id, "text": text})
        elif field["type"] == "bar":
            owner = self.find_by_id(self.owners.get(player.position))
            if owner is None:
                self._queue.append(
                    {
                        "type": "buy",
                        "player_id": player.id,
                        "field": player.position,
                        "price": field["price"],
                    }
                )
            elif owner is not player:
                sips = self.rent(player.position)
                player.sips += sips
                doubled = " – hele farvegruppen!" if sips != field["sips"] else ""
                self._events.append(
                    f"{player.name} drikker {sips_text(sips)} hos {owner.name}{doubled}"
                )

    def _draw_card(self):
        """Every card comes up once before the deck is shuffled again."""
        if not self._deck:
            self._deck = list(self.cards)
            self.rng.shuffle(self._deck)
        return self._deck.pop()["text"]

    def _chooser(self, token, kind):
        player = self.find_by_token(token)
        if player is None:
            raise GameError("Ukendt spiller")
        pending = self.pending
        if not pending or pending["type"] != kind or pending["player_id"] != player.id:
            raise GameError("Det kan du ikke lige nu")
        return player

    def _advance(self):
        """Move on to the next waiting choice, or end the turn if there is none."""
        if self._queue:
            self.pending = self._queue.pop(0)
        else:
            self.pending = None
            self._next_turn()

    def _next_turn(self):
        for _ in self.players:
            self.turn = (self.turn + 1) % len(self.players)
            player = self.players[self.turn]
            if not player.skip_next:
                return
            player.skip_next = False
            self._events.append(f"{player.name} står over efter Brandert-hjørnet")

    def to_dict(self):
        current = self.current_player
        return {
            "started": self.started,
            "players": [p.to_dict() for p in self.players],
            "current_player_id": current.id if current else None,
            "last_roll": self.last_roll,
            "owners": {str(index): owner for index, owner in self.owners.items()},
            "rents": {str(index): self.rent(index) for index in self.owners},
            "pending": self.pending,
            "message": self.message,
        }
