from dataclasses import dataclass, field
from typing import List, Optional
from .card import Card
from .config import STARTING_HEALTH, STARTING_SCORE, STARTING_MAX_SCORE, MAX_SCORE_CAP


@dataclass
class Player:
    name: str
    health: int = STARTING_HEALTH
    max_health: int = STARTING_HEALTH
    score: int = STARTING_SCORE
    max_score: int = STARTING_MAX_SCORE
    hand: List[Card] = field(default_factory=list)
    discard: List[Card] = field(default_factory=list)
    attack_bonus: int = 0
    skip_next_draw: bool = False
    score_locked: bool = False
    team_id: int = 0

    def is_alive(self) -> bool:
        return self.health > 0

    def take_damage(self, amount: int) -> None:
        self.health = max(0, self.health - amount)

    def heal(self, amount: int) -> None:
        self.health = min(self.max_health, self.health + amount)

    def increase_max_score(self, amount: int = 1, cap: Optional[int] = None) -> None:
        if self.score_locked:
            return
        new_val = self.max_score + amount
        if cap is not None:
            new_val = min(new_val, cap)
        self.max_score = new_val

    def decrease_max_score(self, amount: int = 1) -> None:
        if self.score_locked:
            return
        self.max_score = max(1, self.max_score - amount)
        if self.score > self.max_score:
            self.score = self.max_score

    def refill_score_to_max(self) -> None:
        if self.score < self.max_score:
            self.score = self.max_score

    def add_card(self, card: Card) -> None:
        self.hand.append(card)

    def play_card(self, index: int) -> Optional[Card]:
        if 0 <= index < len(self.hand):
            return self.hand.pop(index)
        return None

    def end_turn_cleanup(self) -> None:
        pass

    def to_dict(self, include_hand: bool = True) -> dict:
        hand_count = len(self.hand)
        return {
            "name": self.name,
            "health": self.health,
            "max_health": self.max_health,
            "score": self.score,
            "max_score": self.max_score,
            "attack_bonus": self.attack_bonus,
            "skip_next_draw": self.skip_next_draw,
            "score_locked": self.score_locked,
            "team_id": self.team_id,
            "hand": [c.to_dict() for c in self.hand] if include_hand else [{}] * hand_count,
            "hand_count": hand_count,
            "discard_count": len(self.discard),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        p = cls(name=data["name"])
        p.health = data["health"]
        p.max_health = data["max_health"]
        p.score = data["score"]
        p.max_score = data["max_score"]
        p.team_id = data.get("team_id", 0)
        p.hand = [Card.from_dict(c) for c in data.get("hand", [])]
        return p