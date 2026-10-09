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
    game = make_game(board, 3)
    anna = game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()

    roll = game.roll(anna.token)

    assert anna.position == 3
    assert roll["value"] == 3
    assert roll["field"] == "Chance"
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
    game = make_game(board, 3, 3)
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


def test_board_rejects_bar_without_price(board):
    del board["fields"][1]["price"]
    with pytest.raises(ValueError):
        validate_board(board)


def two_player_game(board, *rolls):
    game = make_game(board, *rolls)
    anna = game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()
    return game, anna, bo


def test_landing_on_a_free_bar_offers_it_and_holds_the_turn(board):
    game, anna, bo = two_player_game(board, 4)

    game.roll(anna.token)

    assert game.pending == {"type": "buy", "player_id": anna.id, "field": 4, "price": 2}
    assert game.current_player is anna
    with pytest.raises(GameError):
        game.roll(anna.token)


def test_buying_a_bar_costs_sips_and_ends_the_turn(board):
    game, anna, bo = two_player_game(board, 4)
    game.roll(anna.token)

    game.buy(anna.token)

    assert game.owners == {4: anna.id}
    assert anna.sips == 2
    assert game.pending is None
    assert game.current_player is bo
    assert game.to_dict()["owners"] == {"4": anna.id}


def test_declining_leaves_the_bar_free(board):
    game, anna, bo = two_player_game(board, 4)
    game.roll(anna.token)

    game.decline(anna.token)

    assert game.owners == {}
    assert anna.sips == 0
    assert game.current_player is bo


def test_only_the_player_on_the_bar_can_buy_it(board):
    game, anna, bo = two_player_game(board, 4)
    game.roll(anna.token)
    with pytest.raises(GameError):
        game.buy(bo.token)
    with pytest.raises(GameError):
        game.decline(bo.token)
    assert game.owners == {}


def test_cannot_buy_without_an_offer(board):
    game, anna, bo = two_player_game(board, 3)
    with pytest.raises(GameError):
        game.buy(anna.token)
    game.roll(anna.token)  # a chance field
    with pytest.raises(GameError):
        game.buy(anna.token)


def test_an_owned_bar_is_not_offered_again(board):
    game, anna, bo = two_player_game(board, 4, 4)
    game.roll(anna.token)
    game.buy(anna.token)

    game.roll(bo.token)

    assert game.pending is None
    assert game.owners == {4: anna.id}
    assert game.current_player is anna


def test_skip_turn_cancels_an_open_offer(board):
    game, anna, bo = two_player_game(board, 4)
    game.roll(anna.token)

    game.skip_turn()

    assert game.pending is None
    assert game.current_player is bo


def test_reset_clears_owners_and_sips(board):
    game, anna, bo = two_player_game(board, 4)
    game.roll(anna.token)
    game.buy(anna.token)

    game.reset()

    assert game.owners == {}
    assert anna.sips == 0


def test_state_never_contains_tokens(board):
    game = make_game(board)
    anna = game.add_player("Anna")
    assert anna.token not in str(game.to_dict())
