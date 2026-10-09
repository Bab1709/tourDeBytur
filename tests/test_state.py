from pathlib import Path

import pytest

from game.state import Game, GameError, load_board, validate_board

BOARD_PATH = Path(__file__).parent.parent / "data" / "board.json"


class FixedDice:
    """Stands in for random.Random and returns the given rolls in order."""

    def __init__(self, *values):
        self.values = list(values)

    def randint(self, low, high):
        return self.values.pop(0)


@pytest.fixture
def board():
    return load_board(BOARD_PATH)


def make_game(board, *rolls):
    return Game(board, rng=FixedDice(*rolls))


def test_board_file_is_a_ring_of_24_fields(board):
    assert len(board["fields"]) == 24
    assert board["fields"][12]["type"] == "brandert"


def test_board_must_begin_with_start(board):
    board["fields"][0] = {"type": "chance", "name": "Chance"}
    with pytest.raises(ValueError):
        validate_board(board)


def test_board_rejects_unknown_group(board):
    board["fields"][1]["group"] = "findes-ikke"
    with pytest.raises(ValueError):
        validate_board(board)


def test_players_get_different_colors_and_tokens(board):
    game = make_game(board)
    anna = game.add_player("Anna")
    bo = game.add_player("Bo")
    assert anna.color != bo.color
    assert anna.token != bo.token
    assert anna.id != bo.id


def test_name_is_trimmed_and_must_be_unique(board):
    game = make_game(board)
    assert game.add_player("  Anna  ").name == "Anna"
    with pytest.raises(GameError):
        game.add_player("anna")
    with pytest.raises(GameError):
        game.add_player("   ")


def test_game_can_fill_up(board):
    game = Game(board, max_players=2)
    game.add_player("Anna")
    game.add_player("Bo")
    with pytest.raises(GameError):
        game.add_player("Carl")


def test_cannot_start_without_players(board):
    with pytest.raises(GameError):
        make_game(board).start()


def test_cannot_roll_before_start(board):
    game = make_game(board, 3)
    anna = game.add_player("Anna")
    with pytest.raises(GameError):
        game.roll(anna.token)


def test_roll_moves_the_piece_and_passes_the_turn(board):
    game = make_game(board, 4)
    anna = game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()

    roll = game.roll(anna.token)

    assert anna.position == 4
    assert roll["value"] == 4
    assert roll["field"] == board["fields"][4]["name"]
    assert roll["passed_start"] is False
    assert game.current_player is bo


def test_only_the_current_player_can_roll(board):
    game = make_game(board, 4)
    game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()
    with pytest.raises(GameError):
        game.roll(bo.token)
    with pytest.raises(GameError):
        game.roll("forkert-token")
    assert bo.position == 0


def test_piece_wraps_around_the_ring(board):
    game = make_game(board, 5)
    anna = game.add_player("Anna")
    game.start()
    anna.position = 22

    roll = game.roll(anna.token)

    assert anna.position == 3
    assert roll["passed_start"] is True


def test_turn_order_goes_around(board):
    game = make_game(board, 1, 1, 1)
    anna = game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()
    game.roll(anna.token)
    game.roll(bo.token)
    assert game.current_player is anna


def test_skip_turn(board):
    game = make_game(board)
    game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()
    game.skip_turn()
    assert game.current_player is bo


def test_reset_keeps_players_and_moves_them_to_start(board):
    game = make_game(board, 4)
    anna = game.add_player("Anna")
    game.start()
    game.roll(anna.token)

    game.reset()

    assert game.started is False
    assert game.players == [anna]
    assert anna.position == 0
    assert game.to_dict()["last_roll"] is None


def test_state_never_contains_tokens(board):
    game = make_game(board)
    anna = game.add_player("Anna")
    assert anna.token not in str(game.to_dict())
