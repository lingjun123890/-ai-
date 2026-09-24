from dataclasses import dataclass, field, asdict
from typing import List, Optional
from .player import Player
from .card import Card
from .deck import Deck
from .config import (HAND_TARGET, MAX_SCORE_CAP, DECK_TOTAL_SIZE,
                     TRAINING_OPPONENT_HP, TRAINING_OPPONENT_MAX_SCORE)
from .renderer import BaseRenderer


@dataclass
class GameState:
    turn_count: int = 0
    current_player_index: int = 0
    is_game_over: bool = False
    winner: Optional[str] = None
    peace_proposer_index: Optional[int] = None
    field_cards: List[dict] = field(default_factory=list)


class GameEngine:
    def __init__(self, player_names: List[str], renderer: Optional[BaseRenderer] = None,
                 deck_scale: float = 1.0, mode: str = "1v1") -> None:
        self.mode = mode
        self.players: List[Player] = [Player(name=n) for n in player_names]
        self.state: GameState = GameState()
        self.renderer: Optional[BaseRenderer] = renderer
        self._played_this_turn: bool = False
        self._turn_played_cards: List[Card] = []

        num = len(self.players)
        self._assign_teams(num, mode)

        self.shared_deck: Deck = Deck()
        self.shared_deck.build_shared_deck(scale=deck_scale)
        self.deck_total_size: int = len(self.shared_deck)

        for p in self.players:
            while len(p.hand) < HAND_TARGET:
                card = self.shared_deck.draw()
                if not card:
                    break
                p.add_card(card)

    def _assign_teams(self, num_players: int, mode: str) -> None:
        if mode in ("1v1", "2v2"):
            for i in range(num_players):
                self.players[i].team_id = i % 2
        elif mode == "4p_free":
            for i in range(num_players):
                self.players[i].team_id = i
        else:
            for i in range(num_players):
                self.players[i].team_id = 0

    @classmethod
    def create_training(cls, player_name: str = "玩家A",
                        opponent_name: str = "模拟目标",
                        renderer: Optional[BaseRenderer] = None,
                        deck_scale: float = 0.5) -> "GameEngine":
        engine = cls([player_name, opponent_name], renderer=renderer, deck_scale=deck_scale)
        bot = engine.players[1]
        bot.max_health = TRAINING_OPPONENT_HP
        bot.health = TRAINING_OPPONENT_HP
        bot.score = 0
        bot.max_score = TRAINING_OPPONENT_MAX_SCORE
        bot.score_locked = True
        bot.training_dummy = True
        bot.hand.clear()
        return engine

    @property
    def current_player(self) -> Player:
        return self.players[self.state.current_player_index]

    def next_player(self) -> None:
        self.state.current_player_index = (
            (self.state.current_player_index + 1) % len(self.players)
        )

    def start_turn(self) -> None:
        self.state.turn_count += 1
        player = self.current_player

        if getattr(player, "training_dummy", False):
            self._played_this_turn = False
            self._turn_played_cards.clear()
            if self.renderer:
                self.renderer.render_turn_start(self)
            return

        if not player.score_locked:
            if player.max_score < MAX_SCORE_CAP:
                player.increase_max_score(1, cap=MAX_SCORE_CAP)
            player.refill_score_to_max()

        self._played_this_turn = False
        self._turn_played_cards.clear()

        while len(player.hand) < HAND_TARGET:
            if player.skip_next_draw:
                player.skip_next_draw = False
                break
            card = self.shared_deck.draw()
            if not card:
                break
            player.add_card(card)

        if self.renderer:
            self.renderer.render_turn_start(self)

    def play_card(self, hand_index: int, target_index: Optional[int] = None) -> bool:
        player = self.current_player
        card = None
        if 0 <= hand_index < len(player.hand):
            card = player.hand[hand_index]

        if card is None:
            if self.renderer:
                self.renderer.render_error("无效的手牌索引")
            return False

        actual_cost = card.get_actual_cost(player, self)

        if player.score < actual_cost:
            if self.renderer:
                self.renderer.render_error(
                    f"积分不足！需要 {actual_cost} 积分，当前只有 {player.score}"
                )
            return False

        if card.needs_target() and target_index is None:
            if self.renderer:
                self.renderer.render_error("这张卡需要选择目标（敌方玩家）")
            return False

        if target_index is not None and 0 <= target_index < len(self.players):
            target_player = self.players[target_index]
            if getattr(player, "team_id", -1) == getattr(target_player, "team_id", -1):
                if self.renderer:
                    self.renderer.render_error("不能对队友使用这张卡！")
                return False

        if not self._played_this_turn:
            self.state.field_cards.clear()
            self._played_this_turn = True

        player.play_card(hand_index)
        player.score -= actual_cost

        target = None
        if target_index is not None and 0 <= target_index < len(self.players):
            target = self.players[target_index]

        if self.renderer:
            self.renderer.render_card_played(player, card, target)

        card.on_play(player, target, engine=self)
        player.discard.append(card)
        self._turn_played_cards.append(card)
        self.state.field_cards.append(card.to_dict())

        if card.card_type == "攻击" and target is not None and target.is_alive() and player.attack_bonus > 0:
            target.take_damage(player.attack_bonus)

        self._check_game_over()
        return True

    def end_turn(self) -> None:
        self.current_player.attack_bonus = 0
        self.current_player.end_turn_cleanup()
        self.next_player()
        if self.renderer:
            self.renderer.render_turn_end(self)
        self.start_turn()

    def _check_game_over(self) -> None:
        alive = [p for p in self.players if p.is_alive()]
        if len(alive) <= 1:
            self.state.is_game_over = True
            self.state.winner = alive[0].name if alive else "平局"
            if self.renderer:
                self.renderer.render_game_over(self)

    def surrender(self, player_index: int) -> None:
        if self.state.is_game_over:
            return
        loser = self.players[player_index]
        winner = next((p for i, p in enumerate(self.players) if i != player_index), None)
        self.state.is_game_over = True
        if winner is not None:
            self.state.winner = winner.name
            if self.renderer:
                self.renderer.render_game_over(self)
        else:
            self.state.winner = f"平局 ({loser.name} 投降)"

    def propose_peace(self, player_index: int) -> None:
        if self.state.is_game_over or self.state.peace_proposer_index is not None:
            return
        self.state.peace_proposer_index = player_index
        proposer = self.players[player_index]
        opponent = self.players[1 - player_index]
        if self.renderer:
            self.renderer.render_info(
                f"{proposer.name} 发起求和，等待 {opponent.name} 同意"
            )

    def accept_peace(self, player_index: int) -> None:
        if self.state.is_game_over:
            return
        if self.state.peace_proposer_index is None:
            return
        if self.state.peace_proposer_index == player_index:
            return
        p1 = self.players[0]
        p2 = self.players[1]
        self.state.is_game_over = True
        self.state.winner = "平局 (双方求和)"
        if self.renderer:
            self.renderer.render_game_over(self)

    def snapshot(self, viewer_index: int, log_tail: Optional[List[str]] = None) -> dict:
        return {
            "viewer_index": viewer_index,
            "players": [
                p.to_dict(include_hand=(i == viewer_index))
                for i, p in enumerate(self.players)
            ],
            "state": asdict(self.state),
            "mode": self.mode,
            "deck_remaining": len(self.shared_deck),
            "deck_total": self.deck_total_size,
            "log_tail": log_tail or [],
        }

    def apply_remote_state(self, data: dict) -> None:
        self.state = GameState(**data["state"])
        if "mode" in data:
            self.mode = data["mode"]
        for i, pd in enumerate(data["players"]):
            if i < len(self.players):
                self.players[i].health = pd["health"]
                self.players[i].max_health = pd["max_health"]
                self.players[i].score = pd["score"]
                self.players[i].max_score = pd["max_score"]
                self.players[i].attack_bonus = pd.get("attack_bonus", 0)
                self.players[i].skip_next_draw = pd.get("skip_next_draw", False)
                self.players[i].score_locked = pd.get("score_locked", False)
                self.players[i].team_id = pd.get("team_id", 0)
                self.players[i].hand = [
                    Card.from_dict(cd) if cd else None for cd in pd.get("hand", [])
                ]
        if "deck_total" in data:
            self.deck_total_size = data["deck_total"]
        if "deck_remaining" in data:
            self.shared_deck.set_remaining(data["deck_remaining"])