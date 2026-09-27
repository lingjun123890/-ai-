from dataclasses import dataclass, field, asdict
from typing import List, Optional
from .player import Player
from .card import Card
from .deck import Deck
from .endless_deck import EndlessDeck
from .config import (HAND_TARGET, MAX_SCORE_CAP, DECK_TOTAL_SIZE,
                     TRAINING_OPPONENT_HP, TRAINING_OPPONENT_MAX_SCORE)
from .renderer import BaseRenderer

ENDLESS_MODES = {"endless_1v1"}
DEATH_REFILL_MODES = {"4p_free", "2v2"}
SOLO_STANDARD_CARD_COUNT = 121


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
        self._deaths_processed: set = set()

        num = len(self.players)
        self._assign_teams(num, mode)

        self.is_endless = mode in ENDLESS_MODES
        if self.is_endless:
            self.shared_deck = EndlessDeck()
            self.deck_total_size = 0
        else:
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
        n = len(self.players)
        for offset in range(1, n + 1):
            candidate = (self.state.current_player_index + offset) % n
            if self.players[candidate].is_alive():
                self.state.current_player_index = candidate
                return
        self.state.current_player_index = 0

    def start_turn(self) -> None:
        self._check_game_over()
        if self.state.is_game_over:
            return

        player = self.current_player
        if not player.is_alive():
            self.next_player()
            player = self.current_player
            if not player.is_alive():
                self._check_game_over()
                return

        self.state.turn_count += 1

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
        if not self.current_player.is_alive():
            if self.renderer:
                self.renderer.render_error("已阵亡玩家无法出牌")
            return False
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

    def _process_new_deaths(self) -> None:
        if self.is_endless:
            return
        new_deaths = [
            (i, p) for i, p in enumerate(self.players)
            if not p.is_alive() and i not in self._deaths_processed
        ]
        if not new_deaths:
            return
        for idx, dead in new_deaths:
            self._deaths_processed.add(idx)
            hand_count = len(dead.hand)
            recovered = list(dead.hand)
            dead.hand.clear()
            self.shared_deck.add_cards(recovered)
            if hasattr(self.shared_deck, "append_solo_standard"):
                self.shared_deck.append_solo_standard()
            if self.renderer:
                self.renderer.render_info(
                    f"{dead.name} 倒下了！回收 {hand_count} 张手牌 + 补充 121 张标准牌库"
                )

    def _check_game_over(self) -> None:
        if self.state.is_game_over:
            return
        alive = [p for p in self.players if p.is_alive()]

        team_ids = {getattr(p, "team_id", i) for i, p in enumerate(self.players)}
        if len(team_ids) > 1 and self.mode in ("2v2",):
            dead_teams = {tid for tid in team_ids
                          if all(not p.is_alive() for p in self.players
                                 if getattr(p, "team_id", -1) == tid)}
            alive_teams = team_ids - dead_teams
            if dead_teams and not alive_teams:
                self.state.is_game_over = True
                self.state.winner = "平局 (全员阵亡)"
                if self.renderer:
                    self.renderer.render_game_over(self)
                return
            if dead_teams and len(alive_teams) == 1:
                win_tid = next(iter(alive_teams))
                win_members = [p.name for p in self.players
                               if getattr(p, "team_id", -1) == win_tid]
                self.state.is_game_over = True
                self.state.winner = "、".join(win_members) + f"（队伍胜利）"
                if self.renderer:
                    self.renderer.render_game_over(self)
                return

        if len(alive) <= 1:
            self.state.is_game_over = True
            self.state.winner = alive[0].name if alive else "平局"
            if self.renderer:
                self.renderer.render_game_over(self)
            return

        self._process_new_deaths()
        if not self.is_endless and len(self.shared_deck) == 0:
            if len(team_ids) > 1 and self.mode in ("2v2",):
                team_hp = {tid: sum(p.health for p in self.players
                                    if getattr(p, "team_id", -1) == tid)
                           for tid in team_ids}
                max_hp = max(team_hp.values())
                top_teams = [tid for tid, v in team_hp.items() if v == max_hp]
                if len(top_teams) == 1:
                    win_members = [p.name for p in self.players
                                   if getattr(p, "team_id", -1) == top_teams[0]]
                    self.state.is_game_over = True
                    self.state.winner = "、".join(win_members) + f"（牌库耗尽，队伍HP最高）"
                    if self.renderer:
                        self.renderer.render_game_over(self)
                    return
                self.state.is_game_over = True
                self.state.winner = "平局 (牌库耗尽)"
                if self.renderer:
                    self.renderer.render_game_over(self)
                return
            max_hp = max(p.health for p in alive)
            top = [p for p in alive if p.health == max_hp]
            self.state.is_game_over = True
            if len(top) == 1:
                self.state.winner = top[0].name
            else:
                self.state.winner = "平局 (牌库耗尽)"
            if self.renderer:
                self.renderer.render_game_over(self)

    def surrender(self, player_index: int) -> None:
        if self.state.is_game_over:
            return
        loser = self.players[player_index]
        self.state.is_game_over = True
        if self.mode in ("2v2",):
            loser_tid = getattr(loser, "team_id", -1)
            winners = [p for p in self.players
                       if getattr(p, "team_id", -1) != loser_tid]
            if winners:
                self.state.winner = "、".join(p.name for p in winners) + f"（{loser.name} 投降）"
            else:
                self.state.winner = f"平局 ({loser.name} 投降)"
        else:
            winner = next((p for i, p in enumerate(self.players) if i != player_index), None)
            self.state.winner = winner.name if winner else f"平局 ({loser.name} 投降)"
        if self.renderer:
            self.renderer.render_game_over(self)

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