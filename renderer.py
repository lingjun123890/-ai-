from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import GameEngine
    from .card import Card
    from .player import Player


class BaseRenderer(ABC):
    @abstractmethod
    def render_intro(self, engine: "GameEngine") -> None: ...

    @abstractmethod
    def render_turn_start(self, engine: "GameEngine") -> None: ...

    @abstractmethod
    def render_card_played(
        self,
        player: "Player",
        card: "Card",
        target: Optional["Player"] = None,
    ) -> None: ...

    @abstractmethod
    def render_turn_end(self, engine: "GameEngine") -> None: ...

    @abstractmethod
    def render_game_over(self, engine: "GameEngine") -> None: ...

    @abstractmethod
    def render_info(self, msg: str) -> None: ...

    @abstractmethod
    def render_error(self, msg: str) -> None: ...