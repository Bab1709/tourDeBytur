from pathlib import Path

import pytest

from game.state import Game, GameError, load_board, load_cards, validate_board

DATA_DIR = Path(__file__).parent.parent / "data"
BOARD_PATH = DATA_DIR / "board.json"


class FixedDice:
    """Stands in for random.Random and returns the given rolls in order."""

    def __init__(self, *values):
        self.values = list(values)

    def randint(self, low, high):
        return self.values.pop(0)

    def shuffle(self, items):
        pass


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


def test_landing_on_another_players_bar_costs_its_sips(board):
    game, anna, bo = two_player_game(board, 4, 4)
    game.roll(anna.token)
    game.buy(anna.token)

    game.roll(bo.token)

    assert bo.sips == 1
    assert "Bo drikker 1 tår hos Anna" in game.message


def test_landing_on_your_own_bar_is_free(board):
    game = make_game(board, 4, 6)
    anna = game.add_player("Anna")
    game.start()
    game.roll(anna.token)
    game.buy(anna.token)
    anna.position = 22

    game.roll(anna.token)

    assert anna.position == 4
    assert anna.sips == 2  # only the price of the bar
    assert game.pending is None


def test_owning_the_whole_group_doubles_the_sips(board):
    game, anna, bo = two_player_game(board, 4)
    game.owners = {4: anna.id}
    assert game.rent(4) == 1
    game.owners = {4: anna.id, 5: bo.id}
    assert game.rent(4) == 1
    game.owners = {4: anna.id, 5: anna.id}
    assert game.rent(4) == 2
    assert game.to_dict()["rents"] == {"4": 2, "5": 2}
    game.turn = 1

    game.roll(bo.token)

    assert bo.sips == 2
    assert "hele farvegruppen" in game.message


def test_passing_start_lets_you_give_sips_to_another_player(board):
    game, anna, bo = two_player_game(board, 5)
    anna.position = 22

    game.roll(anna.token)

    assert game.pending == {"type": "give", "player_id": anna.id, "sips": 2}
    assert game.current_player is anna

    game.give(anna.token, bo.id)

    assert bo.sips == 2
    assert anna.sips == 0
    assert game.pending is None
    assert game.current_player is bo


def test_sips_cannot_be_given_to_yourself_or_nobody(board):
    game, anna, bo = two_player_game(board, 5)
    anna.position = 22
    game.roll(anna.token)
    with pytest.raises(GameError):
        game.give(anna.token, anna.id)
    with pytest.raises(GameError):
        game.give(anna.token, 999)
    with pytest.raises(GameError):
        game.give(bo.token, anna.id)
    assert game.pending["type"] == "give"


def test_passing_start_onto_a_free_bar_asks_both_questions(board):
    game, anna, bo = two_player_game(board, 6)
    anna.position = 22

    game.roll(anna.token)
    assert game.pending["type"] == "give"
    with pytest.raises(GameError):
        game.buy(anna.token)
    game.give(anna.token, bo.id)

    assert game.pending == {"type": "buy", "player_id": anna.id, "field": 4, "price": 2}
    game.buy(anna.token)
    assert game.owners == {4: anna.id}
    assert game.current_player is bo


def test_landing_exactly_on_start_counts_as_passing(board):
    game, anna, bo = two_player_game(board, 2)
    anna.position = 22
    game.roll(anna.token)
    assert game.pending["type"] == "give"


def test_brandert_corner_skips_the_players_next_turn(board):
    game, anna, bo = two_player_game(board, 6, 3, 3)
    anna.position = 6

    game.roll(anna.token)

    assert anna.position == 12
    assert anna.skip_next is True
    assert "glas vand" in game.message

    game.roll(bo.token)  # Anna sits out, so it is Bo again

    assert game.current_player is bo
    assert anna.skip_next is False
    game.roll(bo.token)
    assert game.current_player is anna


def test_brandert_corner_alone_does_not_lock_the_game(board):
    game = make_game(board, 6, 3)
    anna = game.add_player("Anna")
    game.start()
    anna.position = 6
    game.roll(anna.token)
    assert game.current_player is anna
    game.roll(anna.token)
    assert anna.position == 15


def test_skip_turn_drops_all_waiting_choices(board):
    game, anna, bo = two_player_game(board, 6)
    anna.position = 22
    game.roll(anna.token)

    game.skip_turn()

    assert game.pending is None
    assert game.current_player is bo
    assert bo.sips == 0


CARDS = [{"text": "Kort A"}, {"text": "Kort B"}]


def card_game(board, *rolls):
    game = Game(board, CARDS, rng=FixedDice(*rolls))
    anna = game.add_player("Anna")
    bo = game.add_player("Bo")
    game.start()
    return game, anna, bo


def test_chance_file_has_cards():
    cards = load_cards(DATA_DIR / "chance.json")
    assert len(cards) >= 10


def test_chance_card_needs_text(tmp_path):
    path = tmp_path / "chance.json"
    path.write_text('{"cards": [{"text": "  "}]}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_cards(path)


def test_chance_field_draws_a_card_and_holds_the_turn(board):
    game, anna, bo = card_game(board, 3)

    game.roll(anna.token)

    assert game.pending == {"type": "card", "player_id": anna.id, "text": "Kort B"}
    assert "Kort B" in game.message
    assert game.current_player is anna
    with pytest.raises(GameError):
        game.roll(anna.token)


def test_finishing_the_card_ends_the_turn(board):
    game, anna, bo = card_game(board, 3)
    game.roll(anna.token)
    with pytest.raises(GameError):
        game.finish_card(bo.token)

    game.finish_card(anna.token)

    assert game.pending is None
    assert game.current_player is bo


def test_every_card_comes_up_before_any_repeats(board):
    game, anna, bo = card_game(board, 3, 3, 6, 6)
    drawn = []
    for player in (anna, bo, anna, bo):
        game.roll(player.token)
        drawn.append(game.pending["text"])
        game.finish_card(player.token)
    assert sorted(drawn[:2]) == ["Kort A", "Kort B"]
    assert sorted(drawn[2:]) == ["Kort A", "Kort B"]


def test_passing_start_onto_chance_gives_sips_before_the_card(board):
    game, anna, bo = card_game(board, 5)
    anna.position = 22
    game.roll(anna.token)
    assert game.pending["type"] == "give"
    game.give(anna.token, bo.id)
    assert game.pending["type"] == "card"


def test_chance_does_nothing_without_cards(board):
    game, anna, bo = two_player_game(board, 3)
    game.roll(anna.token)
    assert game.pending is None
    assert game.current_player is bo


def test_state_never_contains_tokens(board):
    game = make_game(board)
    anna = game.add_player("Anna")
    assert anna.token not in str(game.to_dict())
