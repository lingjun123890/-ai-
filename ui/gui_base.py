"""GUI 基础组件：常量、工具函数、Settings、Geometry、GUIRenderer、Button"""
import sys
import os
import time
import json
from typing import Optional, List, Tuple, Any, TYPE_CHECKING

import pygame
from pygame.locals import *

from ..renderer import BaseRenderer
from ..network import Network, Message, ConnectionError, DEFAULT_PORT
from ..card import Card

if TYPE_CHECKING:
    from ..engine import GameEngine
    from ..card import Card
    from ..player import Player
from ..network import Network, Message, ConnectionError, DEFAULT_PORT
from ..card import Card
from ..music import MusicManager, scan_audio_folder, format_track_path
from ..credits import CREDITS

if TYPE_CHECKING:
    from ..engine import GameEngine
    from ..card import Card
    from ..player import Player

BASE_W = 1100
BASE_H = 720
MIN_W = 720
MIN_H = 480
FPS = 60

BG_DARK      = (43,  45,  66)
BG_PANEL     = (58,  60,  86)
BG_ACCENT    = (26,  27,  46)
WHITE        = (237, 242, 244)
GRAY_MUTE    = (141, 153, 174)
RED          = (239, 35,  60)
GREEN        = (67,  170, 139)
PURPLE       = (131, 102, 255)
DARK         = (43,  45,  66)
CARD_BACK_CLR = (108, 117, 125)
CARD_BACK_INNER = (80, 87, 97)

CARD_COLOR_MAP = {
    "white":  (245, 245, 245),
    "red":    (255, 204, 204),
    "blue":   (204, 229, 255),
    "green":  (204, 255, 204),
    "yellow": (255, 255, 204),
    "purple": (229, 204, 255),
    "gold":   (255, 235, 170),
}

_FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"


def _load_font(size: int, italic: bool = False) -> pygame.font.Font:
    size = max(8, int(size))
    if os.path.exists(_FONT_PATH):
        font = pygame.font.Font(_FONT_PATH, size)
    else:
        font = pygame.font.SysFont("microsoftyahei", size, italic=italic)
    if italic:
        font.set_italic(True)
    return font


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _get_clipboard_text() -> str:
    try:
        import pygame.scrap
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        raw = pygame.scrap.get("text/plain;charset=utf-8")
        if raw is None:
            raw = pygame.scrap.get("text/plain")
        if raw is None:
            raw = pygame.scrap.get("UTF8_STRING")
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            return str(raw).replace("\x00", "").strip()
    except Exception:
        pass
    return ""


def _sanitize_for_render(s: str) -> str:
    return s.replace("\x00", "")


SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "settings.json")

DEFAULT_SETTINGS = {
    "header_h_ratio": 0.085,
    "footer_h_ratio": 0.15,
    "edge_pad_ratio": 0.02,
    "card_gap_ratio": 0.013,
    "card_count": 5,
    "card_ratio": 120 / 170,
    "music_volume": 0.5,
    "music_folder": "",
    "music_shuffle": False,
    "music_loop": True,
}


def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
    except OSError:
        pass



class Geometry:
    def __init__(self, w: int, h: int, settings: Optional[dict] = None) -> None:
        st = settings or load_settings()
        self.w = max(MIN_W, w)
        self.h = max(MIN_H, h)
        sx = self.w / BASE_W
        sy = self.h / BASE_H
        self.s = min(sx, sy)

        self.header_h  = int(_clamp(st["header_h_ratio"] * self.h, 40, 150))
        self.footer_h  = int(_clamp(st["footer_h_ratio"] * self.h, 70, 250))
        self.edge_pad  = int(_clamp(st["edge_pad_ratio"] * self.w, 8, 50))
        self.line_h    = int(_clamp(22 * sy, 16, 30))

        self.player_panel_h = int(_clamp(self.h * 0.10, 55, 100))
        self.player_panel_gap = int(_clamp(self.edge_pad * 0.4, 6, 16))
        self.top_panel_y = self.header_h + int(self.edge_pad * 0.3)

        self.center_area_x = self.edge_pad
        self.center_area_w = self.w - self.edge_pad * 2
        self.card_gap    = int(_clamp(st["card_gap_ratio"] * self.w, 4, 30))
        self.card_ratio  = st["card_ratio"]

        card_count = st["card_count"]
        available_for_cards = self.w - 2 * self.edge_pad
        self.card_w = int(_clamp(
            (available_for_cards - self.card_gap * (card_count - 1)) / card_count,
            90, 300,
        ))
        self.card_h = int(self.card_w / self.card_ratio)

        self.back_w = int(_clamp(50 * self.s, 28, 80))
        self.back_h = int(self.back_w * 84 / 60)
        self.back_gap = int(_clamp(6 * self.s, 3, 10))

        self.f_title   = int(_clamp(26 * self.s, 14, 40))
        self.f_sub     = int(_clamp(18 * self.s, 12, 26))
        self.f_info    = int(_clamp(16 * self.s, 11, 22))
        self.f_small   = int(_clamp(14 * self.s, 10, 19))
        self.f_cname   = int(_clamp(18 * self.s, 12, 26))
        self.f_cdesc   = int(_clamp(14 * self.s, 10, 20))
        self.f_cflavor = int(_clamp(11 * self.s, 8, 16))
        self.f_ccost   = int(_clamp(18 * self.s, 12, 26))
        self.f_big     = int(_clamp(44 * self.s, 24, 70))

        self.font_title   = _load_font(self.f_title)
        self.font_sub     = _load_font(self.f_sub)
        self.font_info    = _load_font(self.f_info)
        self.font_small   = _load_font(self.f_small)
        self.font_card_name = _load_font(self.f_cname)
        self.font_card_desc = _load_font(self.f_cdesc)
        self.font_card_flavor = _load_font(self.f_cflavor, italic=True)
        self.font_card_cost = _load_font(self.f_ccost)
        self.font_big     = _load_font(self.f_big)



class GUIRenderer(BaseRenderer):
    def __init__(self, game: "Game") -> None:
        self.game = game

    def render_intro(self, engine: "GameEngine") -> None:
        self.game.log("游戏开始！")
        self.game.log(f"共用牌库构建完成: {engine.deck_total_size} 张")
        for p in engine.players:
            self.game.log(f"  · {p.name}")

    def render_turn_start(self, engine: "GameEngine") -> None:
        p = engine.current_player
        self.game.log(f"------- 第 {engine.state.turn_count} 回合 -------")
        self.game.log(
            f"  轮到 {p.name}   max_score 升至 {p.max_score}, 补充至积分 {p.score}"
        )

    def render_card_played(
        self,
        player: "Player",
        card: "Card",
        target: Optional["Player"] = None,
    ) -> None:
        tname = target.name if target else "无目标"
        self.game.log(
            f"→ {player.name} 打出『{card.name}』[{card.card_type}] → {tname}   "
            f"(消耗 {card.cost} 积分, 剩余 {player.score})"
        )

    def render_turn_end(self, engine: "GameEngine") -> None:
        self.game.log(f"  · {engine.current_player.name} 回合结束")

    def render_game_over(self, engine: "GameEngine") -> None:
        self.game.log("=" * 30)
        self.game.log(f"游戏结束！胜者 {engine.state.winner}")
        self.game.show_game_over_overlay(engine.state.winner or "平局")

    def render_info(self, msg: str) -> None:
        self.game.log(msg)

    def render_error(self, msg: str) -> None:
        self.game.log(f"[错误] {msg}")
        self.game.flash_error(msg)



class Button:
    def __init__(self, rect: Rect, text: str, color: Tuple[int, int, int],
                 hover_color: Optional[Tuple[int, int, int]] = None,
                 font: Optional[pygame.font.Font] = None) -> None:
        self.rect = rect
        self.text = text
        self.color = color
        self.hover_color = hover_color or tuple(min(255, c + 30) for c in color)
        self.font = font
        self._hovered = False

    def update(self, mouse_pos: Tuple[int, int]) -> None:
        self._hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surface: pygame.Surface) -> None:
        fill = self.hover_color if self._hovered else self.color
        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        if self._hovered:
            pygame.draw.rect(surface, WHITE, self.rect, 2, border_radius=8)
        txt = self.font.render(self.text, True, WHITE)
        surface.blit(txt, txt.get_rect(center=self.rect.center))

    def is_clicked(self, mouse_pos: Tuple[int, int], mouse_click: bool) -> bool:
        return self.rect.collidepoint(mouse_pos) and mouse_click


# ══════ 开始界面 ══════
