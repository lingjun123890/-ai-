import sys
import os
import time
import json
from typing import Optional, List, Tuple, Any, TYPE_CHECKING

import pygame
from pygame.locals import *

from .renderer import BaseRenderer
from .network import Network, Message, ConnectionError, DEFAULT_PORT
from .card import Card
from .music import MusicManager, scan_audio_folder, format_track_path
from .credits import CREDITS

if TYPE_CHECKING:
    from .engine import GameEngine
    from .card import Card
    from .player import Player

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
class ModeScreen:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("回合计牌游戏")
        self.screen = pygame.display.set_mode((BASE_W, BASE_H), RESIZABLE)
        self.clock = pygame.time.Clock()
        self._g = Geometry(BASE_W, BASE_H)
        self._pending_net: Optional[Network] = None
        self._build_stage_main()

    # ══════ 主菜单（模式选择）══════
    def _build_stage_main(self) -> None:
        g = self._g
        cx = g.w // 2
        btn_w = int(_clamp(min(g.w * 0.5, 380 * g.s), 200, 480))
        btn_h = int(_clamp(max(52 * g.s, g.h * 0.065), 38, 96))
        gap = int(max(g.h * 0.03, 12))
        big_font = _load_font(int(_clamp(28 * g.s, 16, 42)))
        btn_font = _load_font(int(_clamp(22 * g.s, 12, 32)))

        total_h = btn_h * 4 + gap * 3
        start_y = int(g.h * 0.25)

        self.btn_1v1 = Button(
            Rect(cx - btn_w // 2, start_y, btn_w, btn_h),
            "单挑模式", RED, font=big_font,
        )
        self.btn_4p = Button(
            Rect(cx - btn_w // 2, start_y + btn_h + gap, btn_w, btn_h),
            "四人混战", GREEN, font=big_font,
        )
        self.btn_2v2 = Button(
            Rect(cx - btn_w // 2, start_y + (btn_h + gap) * 2, btn_w, btn_h),
            "双人组队对抗", PURPLE, font=big_font,
        )
        self.btn_training = Button(
            Rect(cx - btn_w // 2, start_y + (btn_h + gap) * 3, btn_w, btn_h),
            "训练营地", (241, 196, 15), font=big_font,
        )

        tool_h = int(_clamp(max(44 * g.s, g.h * 0.05), 32, 72))
        tool_gap = int(max(14 * g.s, 8))
        half_btn = (btn_w - tool_gap) // 2
        tool_y = start_y + total_h + int(g.h * 0.05)

        self.btn_settings = Button(
            Rect(cx - btn_w // 2, tool_y, half_btn, tool_h),
            "设置", (52, 73, 94), font=btn_font,
        )
        self.btn_music = Button(
            Rect(cx - btn_w // 2 + half_btn + tool_gap, tool_y, half_btn, tool_h),
            "音乐", (70, 80, 110), font=btn_font,
        )

        quit_y = tool_y + tool_h + int(g.h * 0.025)
        self.btn_quit = Button(
            Rect(cx - btn_w // 2, quit_y, btn_w, tool_h),
            "退出", (108, 117, 125), font=btn_font,
        )

        credit_font = _load_font(int(_clamp(14 * g.s, 10, 20)))
        credit_w = credit_font.size("致谢")[0] + 16
        credit_h = credit_font.get_height() + 8
        self.btn_credits = Button(
            Rect(g.w - credit_w - g.edge_pad, g.h - credit_h - g.edge_pad,
                 credit_w, credit_h),
            "致谢", (50, 55, 75), font=credit_font,
        )

    # ══════ 1v1 子菜单（离线/联机）══════
    def _build_stage_1v1(self) -> None:
        g = self._g
        cx = g.w // 2
        btn_w = int(_clamp(min(g.w * 0.55, 420 * g.s), 220, 520))
        btn_h = int(_clamp(max(54 * g.s, g.h * 0.065), 38, 106))
        gap = int(max(g.h * 0.03, 12))
        btn_font = _load_font(int(_clamp(22 * g.s, 12, 32)))
        big_font = _load_font(int(_clamp(26 * g.s, 14, 38)))

        total_h = btn_h * 4 + gap * 3
        start_y = int(g.h * 0.30)

        self.btn_offline = Button(
            Rect(cx - btn_w // 2, start_y, btn_w, btn_h),
            "离线  同屏轮流对战", RED, font=big_font,
        )
        self.btn_host = Button(
            Rect(cx - btn_w // 2, start_y + btn_h + gap, btn_w, btn_h),
            "联机  成为房主", GREEN, font=big_font,
        )
        self.btn_join = Button(
            Rect(cx - btn_w // 2, start_y + (btn_h + gap) * 2, btn_w, btn_h),
            "联机  成为房客", PURPLE, font=big_font,
        )
        self.btn_relay = Button(
            Rect(cx - btn_w // 2, start_y + (btn_h + gap) * 3, btn_w, btn_h),
            "通过中继联机（零配置）", (241, 196, 15), font=big_font,
        )

        back_w = int(_clamp(140 * g.s, 90, 200))
        back_h = int(_clamp(max(42 * g.s, g.h * 0.05), 30, 70))
        back_y = start_y + total_h + int(g.h * 0.05)
        self.btn_back = Button(
            Rect(cx - back_w // 2, back_y, back_w, back_h),
            "返回", (108, 117, 125), font=btn_font,
        )

    def run(self) -> Optional[Tuple[str, Any]]:
        while True:
            stage = self._main_loop()
            if stage == "1v1":
                result = self._loop_1v1()
                if result is not None:
                    return result
            elif stage == "soon_4p":
                result = self._loop_net_mode("4p_free")
                if result is not None:
                    return result
            elif stage == "soon_2v2":
                result = self._loop_net_mode("2v2")
                if result is not None:
                    return result
            elif stage == "training":
                return ("training", None)
            elif stage == "quit":
                pygame.quit()
                sys.exit(0)

    def _loop_net_mode(self, mode: str) -> Optional[Tuple[str, Any]]:
        choice = self._loop_host_client_choice()
        if choice is None:
            return None
        if choice == "host":
            return self._run_host_lobby(mode)
        else:
            return self._run_client_lobby(mode)

    def _loop_host_client_choice(self) -> Optional[str]:
        cx = self._g.w // 2
        btn_w = int(_clamp(min(self._g.w * 0.55, 420 * self._g.s), 220, 520))
        btn_h = int(_clamp(max(54 * self._g.s, self._g.h * 0.065), 38, 106))
        gap = int(max(self._g.h * 0.035, 14))
        btn_font = _load_font(int(_clamp(22 * self._g.s, 12, 32)))
        big_font = _load_font(int(_clamp(26 * self._g.s, 14, 38)))

        self._build_stage_main()

        host_btn = Button(
            Rect(cx - btn_w // 2, int(self._g.h * 0.35), btn_w, btn_h),
            "成为房主", GREEN, font=big_font,
        )
        join_btn = Button(
            Rect(cx - btn_w // 2, int(self._g.h * 0.35) + btn_h + gap, btn_w, btn_h),
            "成为房客", PURPLE, font=big_font,
        )
        back_btn = Button(
            Rect(cx - btn_w // 2, int(self._g.h * 0.35) + (btn_h + gap) * 2, btn_w, btn_h),
            "返回", (108, 117, 125), font=big_font,
        )

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    return None
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    self._build_stage_main()
                    cx = self._g.w // 2
                    host_btn.rect = Rect(cx - btn_w // 2, int(self._g.h * 0.35), btn_w, btn_h)
                    join_btn.rect = Rect(cx - btn_w // 2, int(self._g.h * 0.35) + btn_h + gap, btn_w, btn_h)
                    back_btn.rect = Rect(cx - btn_w // 2, int(self._g.h * 0.35) + (btn_h + gap) * 2, btn_w, btn_h)
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True

            if mouse_click:
                if host_btn.is_clicked(mouse_pos, True):
                    return "host"
                if join_btn.is_clicked(mouse_pos, True):
                    return "client"
                if back_btn.is_clicked(mouse_pos, True):
                    return None

            self.screen.fill(BG_DARK)
            title = self._g.font_big.render("联机对战", True, WHITE)
            self.screen.blit(title, title.get_rect(center=(self._g.w // 2, int(self._g.h * 0.20))))
            sub = self._g.font_sub.render("请选择你的角色", True, GRAY_MUTE)
            self.screen.blit(sub, sub.get_rect(center=(self._g.w // 2, int(self._g.h * 0.27))))

            for b in [host_btn, join_btn, back_btn]:
                b.update(mouse_pos)
                b.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(FPS)

    def _run_host_lobby(self, mode: str) -> Optional[Tuple[str, Any]]:
        from .network import Network
        net = Network()
        try:
            net.host()
        except OSError as e:
            self._flash(f"无法监听端口: {e}")
            return None

        lobby = LobbyScreen(mode=mode, is_host=True, net=net)
        result = lobby.run()

        if result[0] == "host_start":
            return ("host_start", (net, result[1]))
        net.close()
        return None

    def _run_client_lobby(self, mode: str) -> Optional[Tuple[str, Any]]:
        from .network import Network
        net = self._client_connect_loop()
        if net is None:
            return None
        lobby = LobbyScreen(mode=mode, is_host=False, net=net)
        result = lobby.run()

        if result[0] == "client_start":
            return ("client_start", (net, result[1]))
        net.close()
        return None

    # ══════ 主循环（模式选择）══════
    def _main_loop(self) -> str:
        self._build_stage_main()
        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    return "quit"
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    self._build_stage_main()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
            if mouse_click:
                if self.btn_1v1.is_clicked(mouse_pos, True):
                    return "1v1"
                if self.btn_4p.is_clicked(mouse_pos, True):
                    return "soon_4p"
                if self.btn_2v2.is_clicked(mouse_pos, True):
                    return "soon_2v2"
                if self.btn_training.is_clicked(mouse_pos, True):
                    return "training"
                if self.btn_settings.is_clicked(mouse_pos, True):
                    self._settings_loop()
                    self._build_stage_main()
                if self.btn_music.is_clicked(mouse_pos, True):
                    self._music_loop()
                    self._build_stage_main()
                if self.btn_credits.is_clicked(mouse_pos, True):
                    self._credits_loop()
                    self._build_stage_main()
                if self.btn_quit.is_clicked(mouse_pos, True):
                    return "quit"
            self._draw_main(mouse_pos)
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_main(self, mouse_pos: Tuple[int, int]) -> None:
        g = self._g
        self.screen.fill(BG_DARK)

        title_y = int(g.h * 0.12)
        title = g.font_big.render("回合制卡牌游戏", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(g.w // 2, title_y)))

        sub_y = title_y + title.get_height() + 14
        sub = g.font_sub.render("请选择对战模式", True, GRAY_MUTE)
        self.screen.blit(sub, sub.get_rect(center=(g.w // 2, sub_y)))

        for b in [self.btn_1v1, self.btn_4p, self.btn_2v2, self.btn_training,
                  self.btn_settings, self.btn_music, self.btn_quit, self.btn_credits]:
            b.update(mouse_pos)
            b.draw(self.screen)

    # ══════ 独立音乐界面 ══════
    def _music_loop(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class _Slider:
            rect: Rect
            val: int = 50

            def ratio(self) -> float:
                return _clamp(self.val / 100.0, 0.0, 1.0)

            def x_from_mouse(self, mx: int) -> None:
                r = _clamp((mx - self.rect.x) / self.rect.w, 0.0, 1.0)
                self.val = int(round(r * 100))

        settings = load_settings()
        mm = MusicManager.get()
        mm.load_settings(settings)

        title_font = _load_font(int(_clamp(30 * self._g.s, 18, 44)))
        btn_font = _load_font(int(_clamp(20 * self._g.s, 14, 28)))
        small_font = _load_font(int(_clamp(16 * self._g.s, 11, 24)))

        btn_folder: Optional[Rect] = None
        btn_prev: Optional[Rect] = None
        btn_play: Optional[Rect] = None
        btn_next: Optional[Rect] = None
        btn_shuffle: Optional[Rect] = None
        btn_loop: Optional[Rect] = None
        btn_close: Optional[Rect] = None
        list_rect: Optional[Rect] = None
        path_rect: Optional[Rect] = None
        vol_slider = _Slider(Rect(0, 0, 0, 0), val=int(mm.volume * 100))

        list_scroll: int = 0
        selected_track: int = mm.current_index
        track_rects: List[Rect] = []
        dragging: bool = False

        def _rebuild() -> None:
            nonlocal btn_folder, btn_prev, btn_play, btn_next
            nonlocal btn_shuffle, btn_loop, btn_close, list_rect, path_rect
            nonlocal vol_slider, selected_track

            g = self._g
            gap = int(max(20 * g.s, 14))
            content_w = g.w - gap * 2

            header_h = int(_clamp(80 * g.s, 56, 110))
            title_y = int(g.h * 0.05)

            btn_row_h = int(_clamp(44 * g.s, 32, 58))
            btn_folder = Rect(gap, title_y + header_h, content_w, btn_row_h)

            path_y = btn_folder.bottom + 4
            path_h = small_font.get_height() + 8
            path_rect = Rect(gap, path_y, content_w, path_h)

            info_y = path_rect.bottom + 6
            vol_lbl_h = small_font.get_height()
            vol_track_h = int(max(14 * g.s, 8))
            vol_val_w = max(small_font.size("100%")[0] + 18, 60)
            vol_slider.rect = Rect(
                gap, info_y + vol_lbl_h + 4,
                content_w - vol_val_w - 6, vol_track_h,
            )

            ctrl_y = vol_slider.rect.bottom + int(max(14 * g.s, 10))
            ctrl_w = int(_clamp(80 * g.s, 56, 110))
            ctrl_h = int(_clamp(42 * g.s, 30, 56))
            ctrl_gap = int(_clamp(10 * g.s, 4, 14))
            total_ctrl = ctrl_w * 5 + ctrl_gap * 4
            if total_ctrl > content_w:
                ctrl_w = (content_w - ctrl_gap * 4) // 5
                total_ctrl = ctrl_w * 5 + ctrl_gap * 4
            csx = (g.w - total_ctrl) // 2
            btn_prev = Rect(csx, ctrl_y, ctrl_w, ctrl_h)
            btn_play = Rect(csx + ctrl_w + ctrl_gap, ctrl_y, ctrl_w, ctrl_h)
            btn_next = Rect(csx + (ctrl_w + ctrl_gap) * 2, ctrl_y, ctrl_w, ctrl_h)
            btn_shuffle = Rect(csx + (ctrl_w + ctrl_gap) * 3, ctrl_y, ctrl_w, ctrl_h)
            btn_loop = Rect(csx + (ctrl_w + ctrl_gap) * 4, ctrl_y, ctrl_w, ctrl_h)

            bottom_btn_h = int(_clamp(48 * g.s, 34, 64))
            close_w = int(_clamp(200 * g.s, 140, 280))
            btn_close = Rect((g.w - close_w) // 2,
                             g.h - bottom_btn_h - 16, close_w, bottom_btn_h)

            list_top = btn_loop.bottom + int(max(12 * g.s, 8))
            list_rect = Rect(gap, list_top, content_w,
                             max(40, btn_close.y - 8 - list_top))

        _rebuild()

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_clicked = False

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h, settings=settings)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    title_font = _load_font(int(_clamp(30 * self._g.s, 18, 44)))
                    btn_font = _load_font(int(_clamp(20 * self._g.s, 14, 28)))
                    small_font = _load_font(int(_clamp(16 * self._g.s, 11, 24)))
                    _rebuild()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_clicked = True
                    if vol_slider.rect.collidepoint(mouse_pos):
                        dragging = True
                elif event.type == MOUSEBUTTONUP and event.button == 1:
                    dragging = False
                elif event.type == KEYDOWN and event.key == K_ESCAPE:
                    settings["music_volume"] = mm.volume
                    settings["music_folder"] = mm.folder
                    settings["music_shuffle"] = mm.shuffle
                    settings["music_loop"] = mm.loop
                    save_settings(settings)
                    return
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 4:
                    if list_rect and list_rect.collidepoint(mouse_pos):
                        list_scroll = max(0, list_scroll - 3)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 5:
                    if list_rect and list_rect.collidepoint(mouse_pos):
                        list_scroll += 3

            if dragging:
                vol_slider.x_from_mouse(mouse_pos[0])
                mm.volume = vol_slider.val / 100.0

            if mouse_clicked:
                if btn_folder and btn_folder.collidepoint(mouse_pos):
                    folder = self._pick_folder_dialog()
                    if folder:
                        mm.scan_folder(folder)
                        list_scroll = 0
                        selected_track = mm.current_index

                elif btn_prev and btn_prev.collidepoint(mouse_pos):
                    mm.play_prev()
                    selected_track = mm.current_index
                elif btn_play and btn_play.collidepoint(mouse_pos):
                    mm.play_or_pause()
                    selected_track = mm.current_index
                elif btn_next and btn_next.collidepoint(mouse_pos):
                    mm.play_next()
                    selected_track = mm.current_index
                elif btn_shuffle and btn_shuffle.collidepoint(mouse_pos):
                    mm.shuffle = not mm.shuffle
                elif btn_loop and btn_loop.collidepoint(mouse_pos):
                    mm.loop = not mm.loop

                if list_rect and list_rect.collidepoint(mouse_pos):
                    for i, tr in enumerate(track_rects):
                        if tr.collidepoint(mouse_pos):
                            idx = i + list_scroll
                            if 0 <= idx < len(mm.playlist):
                                selected_track = idx
                                mm.play_index(idx)
                            break

                if btn_close and btn_close.collidepoint(mouse_pos):
                    settings["music_volume"] = mm.volume
                    settings["music_folder"] = mm.folder
                    settings["music_shuffle"] = mm.shuffle
                    settings["music_loop"] = mm.loop
                    save_settings(settings)
                    return

            self.screen.fill(BG_DARK)
            g = self._g

            title_surf = title_font.render("音乐", True, WHITE)
            self.screen.blit(title_surf, title_surf.get_rect(
                center=(g.w // 2, int(g.h * 0.07))))

            folder_btn = Button(btn_folder, "选择音乐文件夹", (52, 73, 94), font=btn_font)
            folder_btn.update(mouse_pos)
            folder_btn.draw(self.screen)

            if path_rect:
                path_text = mm.folder if mm.folder else "(未选择文件夹)"
                if not path_text:
                    path_text = "(未选择文件夹)"
                max_chars = max(1, path_rect.w // (small_font.size("M")[0] + 1))
                if len(path_text) > max_chars:
                    path_text = path_text[:max_chars - 3] + "..."
                path_color = GRAY_MUTE if not mm.folder else (200, 210, 230)
                path_surf = small_font.render(path_text, True, path_color)
                pygame.draw.rect(self.screen, (34, 40, 58), path_rect, border_radius=4)
                self.screen.blit(path_surf, (path_rect.x + 6, path_rect.y + 4))

            lbl_surf = small_font.render(f"音量", True, GRAY_MUTE)
            self.screen.blit(lbl_surf, (vol_slider.rect.x, vol_slider.rect.y - small_font.get_height() - 4))
            pygame.draw.rect(self.screen, (34, 40, 58), vol_slider.rect, border_radius=4)
            r = vol_slider.ratio()
            fill_w = int(vol_slider.rect.w * r)
            pygame.draw.rect(self.screen, (241, 196, 15),
                             Rect(vol_slider.rect.x, vol_slider.rect.y, fill_w, vol_slider.rect.h),
                             border_radius=4)
            handle_x = vol_slider.rect.x + fill_w - 3
            pygame.draw.rect(self.screen, WHITE,
                             Rect(handle_x, vol_slider.rect.y - 3, 6, vol_slider.rect.h + 6),
                             border_radius=2)
            val_surf = small_font.render(f"{vol_slider.val}%", True, WHITE)
            self.screen.blit(val_surf, (vol_slider.rect.right + 6, vol_slider.rect.y - 2))

            def _ctrl_label(i: int) -> str:
                return ["上一首", "暂停", "下一首", "随机", "循环"][i]

            def _ctrl_color(i: int) -> Tuple[int, int, int]:
                if i == 3 and mm.shuffle:
                    return (241, 196, 15)
                if i == 4 and mm.loop:
                    return (241, 196, 15)
                return (70, 80, 110)

            for idx, rct in enumerate([btn_prev, btn_play, btn_next, btn_shuffle, btn_loop]):
                if rct is None:
                    continue
                label = "播放" if (idx == 1 and not mm.is_playing) else _ctrl_label(idx)
                cbtn = Button(rct, label, _ctrl_color(idx), font=small_font)
                cbtn.update(mouse_pos)
                cbtn.draw(self.screen)

            if list_rect:
                pygame.draw.rect(self.screen, (26, 31, 46), list_rect, border_radius=6)
                inner = list_rect.inflate(-4, -4)
                row_h = max(small_font.get_height() + 10, 26)
                track_rects.clear()
                paths = mm.playlist
                visible_count = max(0, inner.h // row_h)
                for vi in range(visible_count):
                    idx = vi + list_scroll
                    if idx >= len(paths):
                        break
                    row_rect = Rect(inner.x, inner.y + vi * row_h, inner.w, row_h)
                    track_rects.append(row_rect)
                    is_selected = (idx == selected_track)
                    is_current = (idx == mm.current_index and mm.is_playing)
                    if is_selected:
                        pygame.draw.rect(self.screen, (52, 73, 94), row_rect, border_radius=3)
                    prefix = "◆" if is_current else ("▶" if is_selected else " ")
                    name = format_track_path(paths[idx], max_len=int(row_rect.w // (small_font.size("M")[0] + 2)))
                    color = (241, 196, 15) if is_current else (220, 225, 235)
                    ns = small_font.render(f"{prefix} {name}", True, color)
                    self.screen.blit(ns, (row_rect.x + 8, row_rect.y + (row_h - ns.get_height()) // 2))

            close_btn = Button(btn_close, "关闭 (ESC)", (108, 117, 125), font=btn_font)
            close_btn.update(mouse_pos)
            close_btn.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(FPS)

    # ══════ 致谢弹窗 ══════
    def _credits_loop(self) -> None:
        g = self._g
        title_font = _load_font(int(_clamp(30 * g.s, 18, 44)))
        header_font = _load_font(int(_clamp(20 * g.s, 14, 28)))
        line_font = _load_font(int(_clamp(17 * g.s, 12, 24)))
        close_font = _load_font(int(_clamp(16 * g.s, 11, 22)))

        panel_w = int(min(g.w * 0.75, 680 * g.s))
        panel_h = int(min(g.h * 0.80, 560 * g.s))
        panel_x = (g.w - panel_w) // 2
        panel_y = (g.h - panel_h) // 2
        panel = Rect(panel_x, panel_y, panel_w, panel_h)

        close_w = close_font.size("关闭 (ESC)")[0] + 24
        close_h = close_font.get_height() + 12
        close_btn = Button(
            Rect(panel.right - close_w - 12, panel.bottom - close_h - 12,
                 close_w, close_h),
            "关闭 (ESC)", (108, 117, 125), font=close_font,
        )

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    g = self._g
                    panel_w = int(min(g.w * 0.75, 680 * g.s))
                    panel_h = int(min(g.h * 0.80, 560 * g.s))
                    panel_x = (g.w - panel_w) // 2
                    panel_y = (g.h - panel_h) // 2
                    panel = Rect(panel_x, panel_y, panel_w, panel_h)
                    close_font = _load_font(int(_clamp(16 * g.s, 11, 22)))
                    close_w = close_font.size("关闭 (ESC)")[0] + 24
                    close_h = close_font.get_height() + 12
                    close_btn = Button(
                        Rect(panel.right - close_w - 12, panel.bottom - close_h - 12,
                             close_w, close_h),
                        "关闭 (ESC)", (108, 117, 125), font=close_font,
                    )
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
                elif event.type == KEYDOWN and event.key == K_ESCAPE:
                    return

            if mouse_click and close_btn.is_clicked(mouse_pos, True):
                return

            self.screen.fill(BG_DARK)

            dim = pygame.Surface((g.w, g.h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            self.screen.blit(dim, (0, 0))

            pygame.draw.rect(self.screen, BG_PANEL, panel, border_radius=12)
            pygame.draw.rect(self.screen, (70, 75, 100), panel, width=2, border_radius=12)

            title_surf = title_font.render("致谢名单", True, WHITE)
            self.screen.blit(title_surf, title_surf.get_rect(
                center=(panel.centerx, panel.y + int(panel.h * 0.08))))

            cur_y = panel.y + int(panel.h * 0.15)
            for header, names in CREDITS:
                hdr = header_font.render(header, True, (241, 196, 15))
                self.screen.blit(hdr, (panel.x + int(panel.w * 0.12), cur_y))
                cur_y += header_font.get_height() + 4
                for name in names:
                    ns = line_font.render(name, True, GRAY_MUTE)
                    self.screen.blit(ns, (panel.x + int(panel.w * 0.16), cur_y))
                    cur_y += line_font.get_height() + 2
                cur_y += int(panel.h * 0.03)

            close_btn.update(mouse_pos)
            close_btn.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(FPS)

    # ══════ 1v1 子循环 ══════
    def _loop_1v1(self) -> Optional[Tuple[str, Any]]:
        self._build_stage_1v1()
        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    self._build_stage_1v1()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
            if mouse_click:
                if self.btn_offline.is_clicked(mouse_pos, True):
                    return ("offline", None)
                if self.btn_host.is_clicked(mouse_pos, True):
                    result = self._run_host_lobby("1v1")
                    if result is not None:
                        return result
                    self._build_stage_1v1()
                if self.btn_join.is_clicked(mouse_pos, True):
                    result = self._run_client_lobby("1v1")
                    if result is not None:
                        return result
                    self._build_stage_1v1()
                if self.btn_relay.is_clicked(mouse_pos, True):
                    net = self._relay_connect_loop()
                    if net is not None:
                        return ("client", net)
                if self.btn_back.is_clicked(mouse_pos, True):
                    return None
            self._draw_1v1(mouse_pos)
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_1v1(self, mouse_pos: Tuple[int, int]) -> None:
        g = self._g
        self.screen.fill(BG_DARK)

        back_title = g.font_small.render("返回主菜单", True, GRAY_MUTE)
        self.screen.blit(back_title, (g.edge_pad, g.edge_pad))

        title_y = int(g.h * 0.15)
        title = g.font_big.render("单挑模式", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(g.w // 2, title_y)))

        sub_y = title_y + title.get_height() + 10
        sub = g.font_sub.render("请选择对战方式", True, GRAY_MUTE)
        self.screen.blit(sub, sub.get_rect(center=(g.w // 2, sub_y)))

        for b in [self.btn_offline, self.btn_host, self.btn_join, self.btn_relay, self.btn_back]:
            b.update(mouse_pos)
            b.draw(self.screen)

    # ══════ 多人联机子菜单 ══════
    def _build_stage_multi_lan(self) -> None:
        g = self._g
        cx = g.w // 2
        btn_w = int(_clamp(min(g.w * 0.55, 420 * g.s), 220, 520))
        btn_h = int(_clamp(max(54 * g.s, g.h * 0.065), 38, 106))
        gap = int(max(g.h * 0.035, 14))
        btn_font = _load_font(int(_clamp(22 * g.s, 12, 32)))
        big_font = _load_font(int(_clamp(26 * g.s, 14, 38)))

        total_h = btn_h * 2 + gap * 1
        start_y = int(g.h * 0.32)

        self.btn_m_host = Button(
            Rect(cx - btn_w // 2, start_y, btn_w, btn_h),
            "成为房主", GREEN, font=big_font,
        )
        self.btn_m_join = Button(
            Rect(cx - btn_w // 2, start_y + btn_h + gap, btn_w, btn_h),
            "成为房客", PURPLE, font=big_font,
        )

        back_w = int(_clamp(140 * g.s, 90, 200))
        back_h = int(_clamp(max(42 * g.s, g.h * 0.05), 30, 70))
        back_y = start_y + total_h + int(g.h * 0.05)
        self.btn_m_back = Button(
            Rect(cx - back_w // 2, back_y, back_w, back_h),
            "返回", (108, 117, 125), font=btn_font,
        )

    def _loop_multi_lan(self, mode_label: str = "多人联机") -> Optional[str]:
        self._build_stage_multi_lan()
        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    self._build_stage_multi_lan()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
            if mouse_click:
                if self.btn_m_host.is_clicked(mouse_pos, True):
                    return "host"
                if self.btn_m_join.is_clicked(mouse_pos, True):
                    net = self._client_connect_loop()
                    if net is not None:
                        self._pending_net = net
                        return "client"
                if self.btn_m_back.is_clicked(mouse_pos, True):
                    return None
            self._draw_multi_lan(mouse_pos, mode_label)
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_multi_lan(self, mouse_pos: Tuple[int, int], mode_label: str) -> None:
        g = self._g
        self.screen.fill(BG_DARK)

        back_title = g.font_small.render("返回主菜单", True, GRAY_MUTE)
        self.screen.blit(back_title, (g.edge_pad, g.edge_pad))

        title_y = int(g.h * 0.15)
        title = g.font_big.render(mode_label, True, WHITE)
        self.screen.blit(title, title.get_rect(center=(g.w // 2, title_y)))

        sub_y = title_y + title.get_height() + 10
        sub = g.font_sub.render("请选择你的角色", True, GRAY_MUTE)
        self.screen.blit(sub, sub.get_rect(center=(g.w // 2, sub_y)))

        for b in [self.btn_m_host, self.btn_m_join, self.btn_m_back]:
            b.update(mouse_pos)
            b.draw(self.screen)

    # ══════ 敬请期待 界面 ══════
    def _loop_coming_soon(self, title_text: str) -> None:
        g = self._g
        back_w = int(_clamp(160 * g.s, 100, 220))
        back_h = int(_clamp(max(46 * g.s, g.h * 0.05), 32, 72))
        back_font = _load_font(int(_clamp(22 * g.s, 12, 32)))
        btn_back = Button(
            Rect(g.w // 2 - back_w // 2, int(g.h * 0.65), back_w, back_h),
            "返回主菜单", (52, 73, 94), font=back_font,
        )

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    g = self._g
                    btn_back = Button(
                        Rect(g.w // 2 - back_w // 2, int(g.h * 0.65), back_w, back_h),
                        "返回主菜单", (52, 73, 94), font=back_font,
                    )
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
            if mouse_click and btn_back.is_clicked(mouse_pos, True):
                return
            self.screen.fill(BG_DARK)
            t = g.font_big.render(title_text, True, WHITE)
            self.screen.blit(t, t.get_rect(center=(g.w // 2, int(g.h * 0.30))))

            big_soon = _load_font(int(_clamp(46 * g.s, 26, 72)))
            soon = big_soon.render("敬请期待", True, (241, 196, 15))
            self.screen.blit(soon, soon.get_rect(center=(g.w // 2, int(g.h * 0.44))))

            dot_font = _load_font(int(_clamp(18 * g.s, 12, 26)))
            dot = dot_font.render("后续版本开发中...", True, GRAY_MUTE)
            self.screen.blit(dot, dot.get_rect(center=(g.w // 2, int(g.h * 0.52))))

            btn_back.update(mouse_pos)
            btn_back.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(FPS)
    # ══════ 设置面板（Tab：界面 / 音乐）══════
    def _settings_loop(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class Slider:
            label: str
            key: str
            min_val: float
            max_val: float
            step: float
            rect: Rect
            val: float = 0.0
            is_int: bool = False

            def ratio(self) -> float:
                if self.max_val == self.min_val:
                    return 0.0
                return (self.val - self.min_val) / (self.max_val - self.min_val)

            def x_from_mouse(self, mx: int) -> None:
                ratio = _clamp((mx - self.rect.x) / self.rect.w, 0.0, 1.0)
                raw = self.min_val + ratio * (self.max_val - self.min_val)
                self.val = round(raw / self.step) * self.step

        settings = load_settings()
        self._g = Geometry(self._g.w, self._g.h, settings=settings)

        title_font = _load_font(int(_clamp(28 * self._g.s, 16, 40)))
        ui_slider_font = _load_font(int(_clamp(18 * self._g.s, 12, 26)))
        ui_value_font = _load_font(int(_clamp(15 * self._g.s, 11, 22)))
        btn_font = _load_font(int(_clamp(20 * self._g.s, 14, 28)))

        ui_slider_rows = [
            ("顶部栏高度", "header_h_ratio", 0.04, 0.20, 0.005),
            ("底部栏高度", "footer_h_ratio", 0.08, 0.30, 0.005),
            ("边缘间距", "edge_pad_ratio", 0.005, 0.06, 0.001),
            ("卡牌间距", "card_gap_ratio", 0.004, 0.04, 0.001),
            ("卡牌宽高比", "card_ratio", 0.55, 0.85, 0.01),
        ]

        ui_sliders: List[Slider] = []
        btn_save_rect: Optional[Rect] = None
        btn_cancel_rect: Optional[Rect] = None
        btn_reset_rect: Optional[Rect] = None
        dragging_slider: Optional[Slider] = None

        def _rebuild() -> None:
            nonlocal btn_save_rect, btn_cancel_rect, btn_reset_rect

            g = self._g
            gap = int(max(20 * g.s, 14))
            btn_h = int(_clamp(48 * g.s, 34, 66))
            btn_w = int(_clamp(160 * g.s, 120, 220))
            bottom_y = g.h - btn_h - 20

            total_btn_w = btn_w * 3 + 20 * 2
            start_x = (g.w - total_btn_w) // 2
            btn_save_rect = Rect(start_x, bottom_y, btn_w, btn_h)
            btn_cancel_rect = Rect(start_x + btn_w + 20, bottom_y, btn_w, btn_h)
            btn_reset_rect = Rect(start_x + (btn_w + 20) * 2, bottom_y, btn_w, btn_h)

            content_top = int(g.h * 0.12)
            content_bottom = bottom_y - gap
            content_h = max(80, content_bottom - content_top)
            content_w = g.w - gap * 2

            ui_sliders.clear()
            left_w = max(int(g.w * 0.38), int(content_w * 0.32))
            slider_area = Rect(gap, content_top, left_w - gap, content_h)
            slider_track_h = int(max(14 * g.s, 8))
            slider_label_h = ui_slider_font.get_height()
            val_w = max(ui_value_font.size("0.200")[0] + 12,
                        ui_value_font.size("100")[0] + 12, 50)
            row_h = max(int(slider_area.h / (len(ui_slider_rows) + 1)), 44)
            sy = slider_area.y
            for label, key, lo, hi, step in ui_slider_rows:
                slider_rect = Rect(slider_area.x, sy + slider_label_h + 4,
                                   slider_area.w - val_w - 6, slider_track_h)
                sl = Slider(label=label, key=key, min_val=lo, max_val=hi,
                            step=step, rect=slider_rect)
                sl.val = float(settings.get(key, DEFAULT_SETTINGS[key]))
                ui_sliders.append(sl)
                sy += row_h

        _rebuild()

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_clicked = False

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h, settings=settings)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    title_font = _load_font(int(_clamp(28 * self._g.s, 16, 40)))
                    ui_slider_font = _load_font(int(_clamp(18 * self._g.s, 12, 26)))
                    ui_value_font = _load_font(int(_clamp(15 * self._g.s, 11, 22)))
                    btn_font = _load_font(int(_clamp(20 * self._g.s, 14, 28)))
                    _rebuild()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_clicked = True
                    for sl in ui_sliders:
                        if sl.rect.collidepoint(mouse_pos):
                            dragging_slider = sl
                            break
                elif event.type == MOUSEBUTTONUP and event.button == 1:
                    dragging_slider = None
                elif event.type == KEYDOWN and event.key == K_ESCAPE:
                    self._g = Geometry(self._g.w, self._g.h)
                    return

            if dragging_slider is not None:
                dragging_slider.x_from_mouse(mouse_pos[0])
                v = int(dragging_slider.val) if dragging_slider.is_int else dragging_slider.val
                settings[dragging_slider.key] = v
                self._g = Geometry(self._g.w, self._g.h, settings=settings)

            if mouse_clicked:
                if btn_save_rect and btn_save_rect.collidepoint(mouse_pos):
                    for sl in ui_sliders:
                        v = int(sl.val) if sl.is_int else sl.val
                        settings[sl.key] = v
                    save_settings(settings)
                    self._g = Geometry(self._g.w, self._g.h)
                    return
                if btn_cancel_rect and btn_cancel_rect.collidepoint(mouse_pos):
                    self._g = Geometry(self._g.w, self._g.h)
                    return
                if btn_reset_rect and btn_reset_rect.collidepoint(mouse_pos):
                    for sl in ui_sliders:
                        sl.val = float(DEFAULT_SETTINGS[sl.key])
                        settings[sl.key] = sl.val
                    self._g = Geometry(self._g.w, self._g.h, settings=settings)
                    _rebuild()

            self.screen.fill(BG_DARK)

            title_surf = title_font.render("设置", True, WHITE)
            self.screen.blit(title_surf, title_surf.get_rect(
                center=(self._g.w // 2, int(self._g.h * 0.06))))

            self._draw_ui_tab(ui_sliders, ui_slider_font, ui_value_font, settings)

            if btn_save_rect and btn_cancel_rect and btn_reset_rect:
                save_b = Button(btn_save_rect, "保存", GREEN, font=btn_font)
                cancel_b = Button(btn_cancel_rect, "取消", (108, 117, 125), font=btn_font)
                reset_b = Button(btn_reset_rect, "恢复默认", PURPLE, font=btn_font)
                save_b.update(mouse_pos)
                cancel_b.update(mouse_pos)
                reset_b.update(mouse_pos)
                save_b.draw(self.screen)
                cancel_b.draw(self.screen)
                reset_b.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(FPS)

    def _pick_folder_dialog(self) -> str:
        import subprocess
        try:
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$d.Description = 'Pick a folder with audio files'; "
                "$d.ShowNewFolderButton = $false; "
                "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                "$d.SelectedPath }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True, timeout=120,
            )
            out_bytes = result.stdout.strip()
            for enc in ("utf-16-le", "utf-8", "gbk", "mbcs"):
                try:
                    decoded = out_bytes.decode(enc).strip()
                    if decoded:
                        return decoded
                except Exception:
                    continue
            return ""
        except Exception:
            return ""

    def _draw_ui_tab(self, sliders: list, label_font, value_font, settings: dict) -> None:
        g = self._g
        for sl in sliders:
            label_surf = label_font.render(sl.label, True, WHITE)
            self.screen.blit(label_surf, (sl.rect.x, sl.rect.y - label_font.get_height() - 6))

            track_h = sl.rect.h
            pygame.draw.rect(self.screen, BG_ACCENT,
                             (sl.rect.x, sl.rect.y, sl.rect.w, track_h),
                             border_radius=track_h // 2)

            fill_w = int(sl.rect.w * sl.ratio())
            if fill_w > 0:
                pygame.draw.rect(self.screen, GREEN,
                                 (sl.rect.x, sl.rect.y, fill_w, track_h),
                                 border_radius=track_h // 2)

            handle_w = int(track_h * 1.6)
            handle_x = sl.rect.x + fill_w - handle_w // 2
            handle_x = int(_clamp(handle_x,
                                  sl.rect.x - handle_w // 2 + track_h // 2,
                                  sl.rect.x + sl.rect.w - handle_w // 2))
            pygame.draw.rect(self.screen, WHITE,
                             (handle_x, sl.rect.y - 2, handle_w, track_h + 4),
                             border_radius=(track_h + 4) // 2)

            val_text = f"{int(sl.val)}" if sl.is_int else f"{sl.val:.3f}"
            val_surf = value_font.render(val_text, True, GRAY_MUTE)
            self.screen.blit(val_surf,
                             (sl.rect.right + 6,
                              sl.rect.y + (track_h - value_font.get_height()) // 2))

        self._draw_settings_preview(settings)

    def _draw_settings_preview(self, settings: dict) -> None:
        g = self._g
        gap = int(max(20 * g.s, 14))
        left_w = max(int(g.w * 0.38), int((g.w - gap * 2) * 0.32))
        right_area_x = left_w
        preview_x = right_area_x + gap
        preview_w = g.w - preview_x - gap

        bottom_y = g.h - int(_clamp(48 * g.s, 34, 66)) - 20
        preview_y = int(g.h * 0.12)
        preview_h = max(80, bottom_y - gap - preview_y)

        preview_margin = int(max(10 * g.s, 6))
        preview_area = Rect(preview_x + preview_margin,
                            preview_y + preview_margin,
                            preview_w - preview_margin * 2,
                            max(40, preview_h - preview_margin * 2))

        pygame.draw.rect(self.screen, BG_PANEL, preview_area,
                         border_radius=int(g.s * 12))
        pygame.draw.rect(self.screen, (70, 75, 100), preview_area,
                         width=2, border_radius=int(g.s * 12))

        pg_x = preview_area.x + 8
        pg_y = preview_area.y + 8
        pg_w = preview_area.w - 16
        pg_h = preview_area.h - 16

        self._draw_mini_preview(pg_x, pg_y, pg_w, pg_h, settings)

    def _draw_mini_preview(self, px: int, py: int, pw: int, ph: int, settings: dict) -> None:
        g = self._g

        scale = min(pw / g.w, ph / g.h)
        off_x = px + (pw - int(g.w * scale)) // 2
        off_y = py + (ph - int(g.h * scale)) // 2

        def sx(v: int) -> int: return int(v * scale)
        def sy(v: int) -> int: return int(v * scale)

        rH = sy(g.header_h)
        rF = sy(g.footer_h)
        rTPY = sy(g.top_panel_y)
        rPH = sy(g.player_panel_h)
        rPPG = sy(g.player_panel_gap)
        rEP = sx(g.edge_pad)
        rCW = sx(g.card_w)
        rCH = sy(g.card_h)
        rCG = sx(g.card_gap)
        rCAX = sx(g.center_area_x)
        rCAW = sx(g.center_area_w)

        mini_font_title = _load_font(max(8, sy(g.f_title)))
        mini_font_sub = _load_font(max(7, sy(g.f_sub)))
        mini_font_card = _load_font(max(6, sy(g.f_ccost)))

        pygame.draw.rect(self.screen, BG_PANEL, (off_x, off_y, sx(g.w), rH))
        pygame.draw.rect(self.screen, (60, 65, 90),
                         (off_x, off_y + rH - max(1, int(scale)), sx(g.w), max(1, int(scale))))
        title_text = mini_font_title.render("回合计牌游戏", True, WHITE)
        info_text = mini_font_sub.render("第 3 回合 · 你的回合 · 牌库 100/108", True, GRAY_MUTE)
        th = title_text.get_height()
        ih = info_text.get_height()
        y_start = max(1, (rH - th - 2 - ih) // 2)
        self.screen.blit(title_text, (off_x + rEP, off_y + y_start))
        self.screen.blit(info_text, (off_x + rEP, off_y + y_start + th + 2))

        pygame.draw.rect(self.screen, BG_PANEL,
                         (off_x, off_y + rTPY, sx(g.w) - 2 * rEP, rPH),
                         border_radius=max(2, int(scale * 4)))
        panel_count = 2
        panel_w = (sx(g.w) - 2 * rEP - rPPG * (panel_count - 1)) // panel_count
        for i, is_me in enumerate([False, True]):
            ppx = off_x + rEP + i * (panel_w + rPPG)
            pygame.draw.rect(self.screen, BG_PANEL, (ppx, off_y + rTPY, panel_w, rPH),
                             border_radius=max(2, int(scale * 4)))
            pygame.draw.rect(self.screen,
                             (52, 211, 153) if is_me else (239, 35, 60),
                             (ppx, off_y + rTPY, panel_w, rPH),
                             max(1, int(scale)), border_radius=max(2, int(scale * 4)))
            tag = "我" if is_me else "对手"
            tag_font = _load_font(max(7, int(rPH * 0.35)))
            tag_surf = tag_font.render(tag, True, WHITE if is_me else GRAY_MUTE)
            self.screen.blit(tag_surf, (ppx + max(2, int(scale * 4)),
                                        off_y + rTPY + max(2, int(scale * 4))))

        play_top = off_y + rTPY + rPH + max(1, int(rEP * 0.4))
        play_bottom = off_y + int(g.h * scale) - rF - rEP
        field_h_available = int((play_bottom - play_top) * 0.28)

        pygame.draw.rect(self.screen, (38, 50, 65),
                         (off_x + rCAX, play_top, rCAW, field_h_available))

        hand_count = 5
        hand_card_w = rCW
        hand_card_h = rCH
        hand_gap = rCG
        total_hand_w = hand_count * hand_card_w + (hand_count - 1) * hand_gap
        if total_hand_w > rCAW - rEP:
            hand_card_w = max(4, int((rCAW - rEP - hand_gap * (hand_count - 1)) / hand_count))
            hand_card_h = max(6, int(hand_card_w / g.card_ratio))
            total_hand_w = hand_count * hand_card_w + (hand_count - 1) * hand_gap

        hand_start_x = off_x + rCAX + (rCAW - total_hand_w) // 2
        hand_y = play_bottom - hand_card_h

        card_colors = [
            (231, 217, 166), (252, 205, 205), (200, 230, 201),
            (218, 208, 255), (255, 236, 179),
        ]
        for i in range(hand_count):
            cx = hand_start_x + i * (hand_card_w + hand_gap)
            cy = hand_y
            card_rect = Rect(cx, cy, hand_card_w, hand_card_h)
            color = card_colors[i % len(card_colors)]
            cr = max(2, int(hand_card_w * 0.08))
            pygame.draw.rect(self.screen, color, card_rect, border_radius=cr)
            pygame.draw.rect(self.screen, (120, 120, 120), card_rect, max(1, int(scale)),
                             border_radius=cr)
            cost_r = max(2, int(hand_card_w * 0.14))
            pygame.draw.circle(self.screen, DARK,
                               (cx + int(hand_card_w * 0.18), cy + int(hand_card_w * 0.18)),
                               cost_r)

        pygame.draw.rect(self.screen, BG_PANEL,
                         (off_x, off_y + int(g.h * scale) - rF, sx(g.w), rF))
        btn_names = ["结束回合", "出牌", "求和", "投降"]
        btn_colors = [GREEN, RED, PURPLE, (108, 117, 125)]
        btn_gap = max(2, int(rEP * 0.3))
        btn_w = (sx(g.w) - 2 * rEP - btn_gap * 3) // 4
        btn_h = max(8, int(rF * 0.55))
        btn_y = off_y + int(g.h * scale) - rF + (rF - btn_h) // 2
        btn_font = _load_font(max(7, int(btn_h * 0.5)))
        for i, name in enumerate(btn_names):
            bx = off_x + rEP + i * (btn_w + btn_gap)
            btn_rect = Rect(bx, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, btn_colors[i], btn_rect,
                             border_radius=max(2, int(scale * 4)))
            txt = btn_font.render(name, True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=btn_rect.center))

    # ══════ Host 等待 ══════
    def _host_wait_loop(self) -> Optional[Network]:
        net = Network()
        try:
            addr = net.host()
        except OSError as e:
            self._flash(f"无法监听端口 {DEFAULT_PORT}: {e}")
            return None

        conn_result: Optional[Network] = None
        error_msg = ""

        def _do_accept() -> None:
            nonlocal conn_result, error_msg
            try:
                net.accept(timeout=300)
                conn_result = net
            except ConnectionError as e:
                error_msg = str(e)
            except OSError as e:
                error_msg = str(e)

        import threading
        t = threading.Thread(target=_do_accept, daemon=True)
        t.start()

        btn_w = int(_clamp(200 * self._g.s, 140, 280))
        btn_h = int(_clamp(54 * self._g.s, 38, 72))
        btn_back = Button(
            Rect(self._g.w // 2 - btn_w // 2, int(self._g.h * 0.62), btn_w, btn_h),
            "返回主菜单", (108, 117, 125), font=_load_font(int(_clamp(20 * self._g.s, 14, 28))),
        )

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    net.close()
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    btn_back.rect = Rect(btn_back.rect.x, int(self._g.h * 0.62), btn_back.rect.w, btn_h)
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True

            if conn_result is not None:
                return conn_result
            if error_msg:
                self._flash(error_msg)
                net.close()
                return None

            if mouse_click and btn_back.is_clicked(mouse_pos, True):
                net.close()
                return None

            self._draw_host_wait(mouse_pos, addr, btn_back, net)
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_host_wait(self, mouse_pos: Tuple[int, int], addr: str, btn_back: Button, net: Network) -> None:
        g = self._g
        self.screen.fill(BG_DARK)

        big = g.font_big.render("等待对手连接...", True, WHITE)
        self.screen.blit(big, big.get_rect(center=(g.w // 2, int(g.h * 0.20))))

        pub = net.public_ip
        port = net.port
        y_cursor = int(g.h * 0.30)
        line_h = int(_clamp(28 * g.s, 20, 38))

        def _center(text: str, y: int, color=WHITE, font=None) -> None:
            f = font or g.font_sub
            s = f.render(text, True, color)
            self.screen.blit(s, s.get_rect(center=(g.w // 2, y)))

        _center("同一 WiFi / 局域网玩家", y_cursor, GRAY_MUTE)
        y_cursor += line_h + 2
        _center(f"内网地址:  {addr}", y_cursor, GREEN, g.font_title)
        y_cursor += line_h + 10

        _center("不同 WiFi / 公网玩家", y_cursor, GRAY_MUTE)
        y_cursor += line_h + 2
        if pub:
            _center(f"公网地址:  {pub}:{port}", y_cursor, (241, 196, 15), g.font_title)
            y_cursor += line_h + 4
            tip1 = g.font_small.render("警告：家庭路由器需做端口转发  外网 TCP", True, (231, 76, 60))
            self.screen.blit(tip1, tip1.get_rect(center=(g.w // 2, y_cursor)))
            y_cursor += line_h - 4
            tip2 = g.font_small.render(f"{port}    → 内网 {net.lan_ip}:{port}", True, (231, 76, 60))
            self.screen.blit(tip2, tip2.get_rect(center=(g.w // 2, y_cursor)))
        else:
            _center("公网 IP 获取失败（请检查网络或手动查询）", y_cursor, (231, 76, 60))
            y_cursor += line_h + 4
            _center(f"手动查询:  https://ip138.com   端口: {port}", y_cursor, GRAY_MUTE, g.font_small)

        btn_back.update(mouse_pos)
        btn_back.draw(self.screen)

    # ══════ Client 输入 ══════
    def _client_connect_loop(self) -> Optional[Network]:
        host_ip = "127.0.0.1"
        host_port = DEFAULT_PORT
        active_field = "ip"
        error_msg = ""

        f_input = _load_font(int(_clamp(26 * self._g.s, 18, 34)))
        f_label = _load_font(int(_clamp(22 * self._g.s, 14, 30)))
        f_btn = _load_font(int(_clamp(22 * self._g.s, 14, 30)))

        input_w = int(_clamp(380 * self._g.s, 260, 460))
        input_h = int(_clamp(52 * self._g.s, 36, 70))
        btn_w = int(_clamp(180 * self._g.s, 120, 240))
        btn_h = int(_clamp(54 * self._g.s, 38, 72))

        ip_rect = Rect(self._g.w // 2 - input_w // 2, int(self._g.h * 0.38), input_w, input_h)
        port_rect = Rect(self._g.w // 2 - input_w // 2, int(self._g.h * 0.50), input_w, input_h)

        btn_connect = Button(
            Rect(self._g.w // 2 - btn_w - 8, int(self._g.h * 0.64), btn_w, btn_h),
            "连接", GREEN, font=f_btn,
        )
        btn_back = Button(
            Rect(self._g.w // 2 + 8, int(self._g.h * 0.64), btn_w, btn_h),
            "返回", (108, 117, 125), font=f_btn,
        )

        blink_timer = 0
        connecting = False
        connect_thread_result: List[Optional[Network]] = [None]
        connect_error: List[str] = [""]

        def _do_connect() -> None:
            try:
                h = host_ip.strip()
                p = host_port
                if ":" in h and not h.startswith("["):
                    parts = h.rsplit(":", 1)
                    h = parts[0].strip()
                    try:
                        p = int(parts[1].strip())
                    except ValueError:
                        pass
                if not h:
                    connect_error[0] = "请输入房间 IP 地址"
                    return
                net = Network()
                net.connect(h, p)
                connect_thread_result[0] = net
            except ConnectionError as e:
                connect_error[0] = str(e)
            except OSError as e:
                connect_error[0] = str(e)

        import threading

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            blink_timer += 1

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
                    if ip_rect.collidepoint(mouse_pos):
                        active_field = "ip"
                    elif port_rect.collidepoint(mouse_pos):
                        active_field = "port"
                    elif btn_connect.is_clicked(mouse_pos, True) and not connecting:
                        connecting = True
                        connect_thread_result[0] = None
                        connect_error[0] = ""
                        threading.Thread(target=_do_connect, daemon=True).start()
                    elif btn_back.is_clicked(mouse_pos, True):
                        return None
                elif event.type == KEYDOWN and not connecting:
                    if event.key == K_TAB:
                        active_field = "port" if active_field == "ip" else "ip"
                    elif event.key == K_ESCAPE:
                        return None
                    elif event.key == K_BACKSPACE:
                        if active_field == "ip" and host_ip:
                            host_ip = host_ip[:-1]
                        elif active_field == "port" and len(str(host_port)) > 0:
                            s = str(host_port)[:-1]
                            host_port = int(s) if s else 0
                    elif event.key == K_v and (pygame.key.get_mods() & (KMOD_CTRL | KMOD_META)):
                        pasted = _get_clipboard_text().strip()
                        if pasted:
                            if active_field == "ip":
                                host_ip += pasted
                            elif active_field == "port":
                                digits = "".join(c for c in pasted if c.isdigit())
                                if digits:
                                    host_port = int(digits)
                    elif event.key == K_RETURN:
                        if not connecting:
                            connecting = True
                            connect_thread_result[0] = None
                            connect_error[0] = ""
                            threading.Thread(target=_do_connect, daemon=True).start()
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            if active_field == "ip" and (ch.isdigit() or ch == "." or ch == ":" or ch.isalpha() or ch == "-"):
                                host_ip += ch
                            elif active_field == "port" and ch.isdigit():
                                host_port = host_port * 10 + int(ch)

            if connecting and connect_thread_result[0] is not None:
                return connect_thread_result[0]
            if connecting and connect_error[0]:
                error_msg = connect_error[0]
                connecting = False

            self._draw_client(
                mouse_pos, host_ip, host_port, active_field, connecting,
                ip_rect, port_rect, btn_connect, btn_back, f_input, f_label,
                blink_timer, error_msg,
            )
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_client(
        self, mouse_pos, host_ip, host_port, active_field, connecting,
        ip_rect, port_rect, btn_connect, btn_back, f_input, f_label,
        blink_timer, error_msg,
    ) -> None:
        g = self._g
        self.screen.fill(BG_DARK)
        title = g.font_big.render("加入游戏", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(g.w // 2, int(g.h * 0.22))))
        sub = g.font_sub.render("输入房主 IP 地址和端口（回车/Tab 切换焦点）", True, GRAY_MUTE)
        self.screen.blit(sub, sub.get_rect(center=(g.w // 2, int(g.h * 0.30))))

        for label, rect, text, active in [
            ("房主 IP", ip_rect, host_ip, active_field == "ip"),
            ("端口", port_rect, str(host_port) if host_port else "", active_field == "port"),
        ]:
            label_surf = f_label.render(label, True, GRAY_MUTE)
            self.screen.blit(label_surf, (rect.x, rect.y - label_surf.get_height() - 4))
            border_c = GREEN if active else GRAY_MUTE
            pygame.draw.rect(self.screen, BG_PANEL, rect, border_radius=6)
            pygame.draw.rect(self.screen, border_c, rect, 2, border_radius=6)
            text = text.replace("\x00", "")
            txt_surf = f_input.render(text, True, WHITE)
            self.screen.blit(txt_surf, (rect.x + 12, rect.y + (rect.h - txt_surf.get_height()) // 2))
            if active and blink_timer % (FPS * 2) < FPS:
                cursor_x = rect.x + 12 + txt_surf.get_width() + 2
                pygame.draw.line(
                    self.screen, WHITE,
                    (cursor_x, rect.y + 8), (cursor_x, rect.y + rect.h - 8), 2,
                )

        if connecting:
            w = int(_clamp(260 * g.s, 180, 340))
            h = int(_clamp(46 * g.s, 32, 60))
            rect = Rect(g.w // 2 - w // 2, int(g.h * 0.64), w, h)
            pygame.draw.rect(self.screen, PURPLE, rect, border_radius=6)
            txt = g.font_sub.render("连接中..", True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
        else:
            btn_connect.update(mouse_pos)
            btn_connect.draw(self.screen)
            btn_back.update(mouse_pos)
            btn_back.draw(self.screen)

        if error_msg:
            err = g.font_info.render(error_msg, True, RED)
            self.screen.blit(err, err.get_rect(center=(g.w // 2, int(g.h * 0.76))))

    # ══════ 中继服务器连接 ══════
    def _relay_connect_loop(self) -> Optional[Network]:
        relay_host = ""
        relay_port = 9998
        room_id = ""
        active_field = "host"
        error_msg = ""

        f_input = _load_font(int(_clamp(26 * self._g.s, 18, 34)))
        f_label = _load_font(int(_clamp(22 * self._g.s, 14, 30)))
        f_btn = _load_font(int(_clamp(22 * self._g.s, 14, 30)))

        input_w = int(_clamp(380 * self._g.s, 260, 460))
        input_h = int(_clamp(52 * self._g.s, 36, 70))
        btn_w = int(_clamp(180 * self._g.s, 120, 240))
        btn_h = int(_clamp(54 * self._g.s, 38, 72))

        g = self._g
        host_rect = Rect(g.w // 2 - input_w // 2, int(g.h * 0.34), input_w, input_h)
        port_rect = Rect(g.w // 2 - input_w // 2, int(g.h * 0.48), input_w // 2 - 4, input_h)
        room_rect = Rect(g.w // 2 - input_w // 2, int(g.h * 0.60), input_w, input_h)

        btn_connect = Button(
            Rect(g.w // 2 - btn_w - 8, int(g.h * 0.74), btn_w, btn_h),
            "连接", GREEN, font=f_btn,
        )
        btn_back = Button(
            Rect(g.w // 2 + 8, int(g.h * 0.74), btn_w, btn_h),
            "返回", (108, 117, 125), font=f_btn,
        )

        blink_timer = 0
        connecting = False
        waiting = False
        wait_txt = ""
        thread_result: List[Optional[Network]] = [None]
        thread_error: List[str] = [""]

        def _do_relay() -> None:
            try:
                h = relay_host.strip()
                p = relay_port
                if ":" in h and not h.startswith("["):
                    parts = h.rsplit(":", 1)
                    h = parts[0].strip()
                    try:
                        p = int(parts[1].strip())
                    except ValueError:
                        pass
                if not h:
                    thread_error[0] = "请输入中继服务器地址"
                    return
                net = Network()
                net.relay_connect(h, p, room_id.strip())
                thread_result[0] = net
            except ConnectionError as e:
                thread_error[0] = str(e)
            except OSError as e:
                thread_error[0] = str(e)

        import threading

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            blink_timer += 1

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    g = self._g
                    host_rect = Rect(g.w // 2 - input_w // 2, int(g.h * 0.34), input_w, input_h)
                    port_rect = Rect(g.w // 2 - input_w // 2, int(g.h * 0.48), input_w // 2 - 4, input_h)
                    room_rect = Rect(g.w // 2 - input_w // 2, int(g.h * 0.60), input_w, input_h)
                    btn_connect.rect = Rect(g.w // 2 - btn_w - 8, int(g.h * 0.74), btn_w, btn_h)
                    btn_back.rect = Rect(g.w // 2 + 8, int(g.h * 0.74), btn_w, btn_h)
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
                    if not connecting:
                        if host_rect.collidepoint(mouse_pos):
                            active_field = "host"
                        elif port_rect.collidepoint(mouse_pos):
                            active_field = "port"
                        elif room_rect.collidepoint(mouse_pos):
                            active_field = "room"
                        elif btn_connect.is_clicked(mouse_pos, True):
                            if relay_host.strip() and room_id.strip():
                                connecting = True
                                thread_result[0] = None
                                thread_error[0] = ""
                                threading.Thread(target=_do_relay, daemon=True).start()
                        elif btn_back.is_clicked(mouse_pos, True):
                            return None
                elif event.type == KEYDOWN and not connecting:
                    if event.key == K_TAB:
                        order = ["host", "port", "room"]
                        active_field = order[(order.index(active_field) + 1) % len(order)]
                    elif event.key == K_ESCAPE:
                        return None
                    elif event.key == K_BACKSPACE:
                        if active_field == "host" and relay_host:
                            relay_host = relay_host[:-1]
                        elif active_field == "port":
                            s = str(relay_port)[:-1]
                            relay_port = int(s) if s else 0
                        elif active_field == "room" and room_id:
                            room_id = room_id[:-1]
                    elif event.key == K_v and (pygame.key.get_mods() & (KMOD_CTRL | KMOD_META)):
                        pasted = _get_clipboard_text().strip()
                        if pasted:
                            if active_field == "host":
                                relay_host += pasted
                            elif active_field == "port":
                                digits = "".join(c for c in pasted if c.isdigit())
                                if digits:
                                    relay_port = int(digits)
                            elif active_field == "room":
                                cleaned = "".join(
                                    c for c in pasted
                                    if c.isdigit() or c.isalpha() or c == "-" or c == "_"
                                )
                                room_id += cleaned[: 24 - len(room_id)]
                    elif event.key == K_RETURN:
                        if relay_host.strip() and room_id.strip() and not connecting:
                            connecting = True
                            thread_result[0] = None
                            thread_error[0] = ""
                            threading.Thread(target=_do_relay, daemon=True).start()
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            if active_field == "host" and (ch.isdigit() or ch == "." or ch.isalpha() or ch == "-" or ch == ":"):
                                relay_host += ch
                            elif active_field == "port" and ch.isdigit():
                                relay_port = relay_port * 10 + int(ch)
                            elif active_field == "room" and (ch.isdigit() or ch.isalpha() or ch == "-" or ch == "_"):
                                if len(room_id) < 24:
                                    room_id += ch

            if connecting and thread_result[0] is not None:
                return thread_result[0]
            if connecting and thread_error[0]:
                error_msg = thread_error[0]
                connecting = False

            self._draw_relay(
                mouse_pos, relay_host, relay_port, room_id, active_field,
                connecting, host_rect, port_rect, room_rect,
                btn_connect, btn_back, f_input, f_label, blink_timer, error_msg,
            )
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_relay(
        self, mouse_pos, relay_host, relay_port, room_id, active_field,
        connecting, host_rect, port_rect, room_rect,
        btn_connect, btn_back, f_input, f_label, blink_timer, error_msg,
    ) -> None:
        g = self._g
        self.screen.fill(BG_DARK)

        back_title = g.font_small.render("返回", True, GRAY_MUTE)
        self.screen.blit(back_title, (g.edge_pad, g.edge_pad))

        title = g.font_big.render("通过中继联机", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(g.w // 2, int(g.h * 0.18))))
        sub = g.font_sub.render("双方填入同一个中继地址 + 同一个房间号即可对战", True, GRAY_MUTE)
        self.screen.blit(sub, sub.get_rect(center=(g.w // 2, int(g.h * 0.25))))

        hint = g.font_info.render("中继服务器需自建（部署到有公网 IP 的机器）", True, (200, 170, 110))
        self.screen.blit(hint, hint.get_rect(center=(g.w // 2, int(g.h * 0.30))))

        fields = [
            ("中继 IP / 域名", host_rect, relay_host, active_field == "host"),
            ("端口", port_rect, str(relay_port) if relay_port else "", active_field == "port"),
            ("房间号（双方一致）", room_rect, room_id, active_field == "room"),
        ]
        for label, rect, text, active in fields:
            label_surf = f_label.render(label, True, GRAY_MUTE)
            self.screen.blit(label_surf, (rect.x, rect.y - label_surf.get_height() - 4))
            border_c = GREEN if active else GRAY_MUTE
            pygame.draw.rect(self.screen, BG_PANEL, rect, border_radius=6)
            pygame.draw.rect(self.screen, border_c, rect, 2, border_radius=6)
            if not text:
                placeholder_color = (90, 100, 115)
                ph = ""
                if label == "中继 IP / 域名":
                    ph = "例如 relay.example.com"
                elif label == "房间号（双方一致）":
                    ph = "例如 42"
                elif label == "端口":
                    ph = "9998"
                placeholder = f_input.render(ph, True, placeholder_color)
                self.screen.blit(placeholder, (rect.x + 12, rect.y + (rect.h - placeholder.get_height()) // 2))
                cursor_w = placeholder.get_width() if ph else 0
            else:
                text = text.replace("\x00", "")
                txt_surf = f_input.render(text, True, WHITE)
                self.screen.blit(txt_surf, (rect.x + 12, rect.y + (rect.h - txt_surf.get_height()) // 2))
                cursor_w = txt_surf.get_width()
            if active and not connecting and blink_timer % (FPS * 2) < FPS:
                cursor_x = rect.x + 12 + cursor_w + 2
                pygame.draw.line(
                    self.screen, WHITE,
                    (cursor_x, rect.y + 8), (cursor_x, rect.y + rect.h - 8), 2,
                )

        if connecting:
            w = int(_clamp(320 * g.s, 220, 420))
            h = int(_clamp(46 * g.s, 32, 60))
            rect = Rect(g.w // 2 - w // 2, int(g.h * 0.74), w, h)
            pygame.draw.rect(self.screen, PURPLE, rect, border_radius=6)
            txt = g.font_sub.render("连接中 / 等待对手加入...", True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
        else:
            btn_connect.update(mouse_pos)
            btn_connect.draw(self.screen)
            btn_back.update(mouse_pos)
            btn_back.draw(self.screen)

        if error_msg:
            err = g.font_info.render(error_msg, True, RED)
            self.screen.blit(err, err.get_rect(center=(g.w // 2, int(g.h * 0.86))))

    def _flash(self, msg: str) -> None:
        self._g = Geometry(self._g.w, self._g.h)
        start = time.time()
        while time.time() - start < 1.5:
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
            self.screen.fill(BG_DARK)
            big = self._g.font_title.render(msg, True, RED)
            self.screen.blit(big, big.get_rect(center=(self._g.w // 2, self._g.h // 2)))
            pygame.display.flip()
            self.clock.tick(FPS)


# ══════ 等待房间（联机大厅 · 真实 P2P 实时同步） ══════
TEAM_A_COLOR = (67, 170, 139)
TEAM_B_COLOR = (239, 35, 60)
FFA_COLORS = [(67, 170, 139), (239, 35, 60), (131, 102, 255), (241, 196, 15)]


def _assign_teams(num_players: int, mode: str) -> list:
    if mode == "1v1":
        return [0, 1]
    elif mode == "2v2":
        return [0, 1, 0, 1, 0, 1][:num_players]
    elif mode == "4p_free":
        return list(range(num_players))
    return [0] * num_players


def _team_color(team_id: int, mode: str) -> tuple:
    if mode in ("1v1", "2v2"):
        return TEAM_A_COLOR if team_id == 0 else TEAM_B_COLOR
    return FFA_COLORS[team_id % len(FFA_COLORS)]


def _serialize_players(players: list) -> list:
    return [{"name": p["name"], "ready": p["ready"], "is_me": p["is_me"], "connected": p.get("connected", True)} for p in players]


def _deserialize_players(raw: list, my_name: str = "") -> list:
    result = []
    for i, p in enumerate(raw):
        d = {"name": p.get("name", f"玩家{i}"), "ready": p.get("ready", False),
             "is_me": bool(p.get("is_me", False)), "connected": p.get("connected", True)}
        result.append(d)
    if my_name:
        for d in result:
            if d["name"] == my_name:
                d["is_me"] = True
                break
    return result


_LOBBY_DEFAULT_NAMES = {
    "1v1":       ("房主", "房客"),
    "2v2":       ("房主", "房客1", "房客2", "房客3"),
    "4p_free":   ("房主", "房客1", "房客2", "房客3"),
}


class LobbyScreen:
    def __init__(self, mode: str = "1v1", is_host: bool = True,
                 room_id: str = "", net: Optional["Network"] = None,
                 my_name: str = "", host_address: str = "") -> None:
        from .network import Network
        self.mode = mode
        self.is_host = is_host
        self.room_id = room_id or "AUTO"
        self.net: Optional[Network] = net
        self.my_name = my_name or ("房主" if is_host else "房客")
        self.host_address = host_address

        self.mode_caps = {
            "1v1":       ("单挑", 2),
            "2v2":       ("双人组队对抗", 4),
            "4p_free":   ("四人混战", 4),
        }
        self.mode_label, self.max_players = self.mode_caps.get(mode, ("房间", 4))

        if is_host:
            self.players: list = [
                {"name": self.my_name, "ready": False, "is_me": True, "connected": True},
            ]
        else:
            self.players = [
                {"name": "房主", "ready": False, "is_me": False, "connected": True},
            ]

        self._accepted_peer_indices: List[int] = []
        self._game_started = False
        self._start_payload: Optional[dict] = None
        self._connect_error: str = ""
        self._name_edit_active: bool = False

        self._g = Geometry(BASE_W, BASE_H)
        self.clock = pygame.time.Clock()

    def can_start(self) -> bool:
        if not self.is_host:
            return False
        if len(self.players) < 2:
            return False
        return all(p.get("ready", True) for p in self.players if p.get("connected", True))

    def min_players_to_start(self) -> int:
        if self.mode == "1v1":
            return 2
        return 2

    def _host_tick_network(self) -> None:
        if self.net is None:
            return

        connected_now = len(self.net._peer_socks)
        known_peers = set(self._accepted_peer_indices)

        for peer_idx in range(connected_now):
            if peer_idx in known_peers:
                continue
            self._accepted_peer_indices.append(peer_idx)
            default_names = _LOBBY_DEFAULT_NAMES.get(self.mode, ("房主",))
            idx_in_players = len(self.players)
            name = default_names[idx_in_players] if idx_in_players < len(default_names) else f"房客{peer_idx+1}"
            self.players.append({
                "name": name, "ready": False, "is_me": False, "connected": True,
            })
            self._lobby_broadcast()

        for i, peer_idx in enumerate(self._accepted_peer_indices):
            if peer_idx >= connected_now:
                continue
            for msg in self.net.poll_peer(peer_idx):
                if msg.type == "JOIN":
                    client_name = msg.payload.get("name", "")
                    if client_name and peer_idx + 1 < len(self.players):
                        default_guest_names = {"房客", "玩家"}
                        if client_name not in default_guest_names:
                            self.players[peer_idx + 1]["name"] = client_name
                        self._lobby_broadcast()
                elif msg.type == "READY":
                    ready_val = bool(msg.payload.get("ready", False))
                    if peer_idx + 1 < len(self.players):
                        self.players[peer_idx + 1]["ready"] = ready_val
                    self._lobby_broadcast()

    def _lobby_broadcast(self) -> None:
        if self.net is None:
            return
        for peer_idx in range(len(self.net._peer_socks)):
            players_for_peer = []
            for i, p in enumerate(self.players):
                players_for_peer.append({
                    "name": p["name"],
                    "ready": p["ready"],
                    "connected": p.get("connected", True),
                    "is_me": (i == peer_idx + 1),
                    "slot_index": i,
                })
            try:
                self.net.send_to(peer_idx, Message("STATE_LOBBY", {
                    "players": players_for_peer,
                    "mode": self.mode,
                    "max_players": self.max_players,
                }))
            except ConnectionError:
                pass

    def _client_tick_network(self) -> None:
        if self.net is None:
            return
        for msg in self.net.recv_all():
            if msg.type == "STATE_LOBBY":
                raw = msg.payload.get("players", [])
                self.players = _deserialize_players(raw, my_name=None)
                self.mode = msg.payload.get("mode", self.mode)
                self.max_players = msg.payload.get("max_players", self.max_players)
            elif msg.type == "START":
                self._game_started = True
                self._start_payload = msg.payload

    def run(self) -> Tuple[str, dict]:
        pygame.display.set_caption(f"联机大厅 · {self.mode_label}")
        self.screen = pygame.display.set_mode((BASE_W, BASE_H), RESIZABLE)
        self._g = Geometry(BASE_W, BASE_H)
        clock = pygame.time.Clock()

        if self.is_host:
            need = self.max_players - 1
            if self.net is not None:
                self.net.start_accept_loop(max_players=need)
                self._lobby_broadcast()
        else:
            if self.net is not None:
                try:
                    self.net.send(Message("JOIN", {"name": self.my_name}))
                except ConnectionError:
                    pass

        self._build_buttons()

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False
            for event in pygame.event.get():
                if event.type == QUIT:
                    if self.net is not None:
                        self.net.close()
                    return ("quit", {})
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    self._build_buttons()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True

            if self.is_host:
                self._host_tick_network()
            else:
                self._client_tick_network()
                if self._game_started:
                    payload = self._start_payload or {}
                    return ("client_start", payload)

            if mouse_click:
                if self.btn_back.is_clicked(mouse_pos, True):
                    if self.net is not None:
                        self.net.close()
                    return ("back", {})
                if self.btn_ready.is_clicked(mouse_pos, True):
                    me_idx = next((i for i, p in enumerate(self.players) if p["is_me"]), 0)
                    new_ready = not self.players[me_idx]["ready"]
                    self.players[me_idx]["ready"] = new_ready
                    if self.is_host:
                        self._lobby_broadcast()
                    elif self.net is not None:
                        try:
                            self.net.send(Message("READY", {"ready": new_ready}))
                        except ConnectionError:
                            pass
                if self.is_host and self.btn_start.is_clicked(mouse_pos, True):
                    if self.can_start():
                        payload = {
                            "mode": self.mode,
                            "player_names": [p["name"] for p in self.players if p.get("connected", True)],
                            "num_players": sum(1 for p in self.players if p.get("connected", True)),
                        }
                        self._host_send_start(payload)
                        if self.net is not None:
                            self.net.stop_accept_loop()
                        return ("host_start", payload)

            self._draw(mouse_pos)
            pygame.display.flip()
            clock.tick(FPS)

    def _host_send_start(self, payload: dict) -> None:
        if self.net is None:
            return
        names = payload["player_names"]
        for client_idx in range(self.net.peer_count):
            try:
                self.net.send_to(client_idx, Message("START", {
                    "client_index": client_idx + 1,
                    "player_names": names,
                }))
            except ConnectionError:
                pass

    def _build_buttons(self) -> None:
        g = self._g
        big_font = _load_font(int(_clamp(28 * g.s, 16, 42)))
        btn_font = _load_font(int(_clamp(22 * g.s, 12, 32)))

        back_w = int(_clamp(140 * g.s, 90, 200))
        back_h = int(_clamp(max(42 * g.s, g.h * 0.05), 30, 70))
        self.btn_back = Button(
            Rect(g.edge_pad, g.edge_pad, back_w, back_h),
            "返回", (108, 117, 125), font=btn_font,
        )

        start_w = int(_clamp(220 * g.s, 140, 320))
        start_h = int(_clamp(max(52 * g.s, g.h * 0.06), 36, 86))
        self.btn_start = Button(
            Rect(g.w - g.edge_pad - start_w, g.h - g.edge_pad - start_h, start_w, start_h),
            "开始游戏" if self.is_host else "等待房主...",
            (46, 204, 113) if self.is_host else (75, 80, 110),
            font=big_font,
        )
        self.btn_ready = Button(
            Rect(g.w // 2 - int(_clamp(160 * g.s, 100, 240)) // 2,
                 g.h - g.edge_pad - start_h,
                 int(_clamp(160 * g.s, 100, 240)), start_h),
            "⏳ 未准备", (241, 196, 15), font=btn_font,
        )

    def _draw(self, mouse_pos: Tuple[int, int]) -> None:
        g = self._g
        self.screen.fill(BG_DARK)

        title_font = _load_font(int(_clamp(36 * g.s, 20, 52)))
        sub_font = _load_font(int(_clamp(20 * g.s, 12, 28)))

        title_y = int(g.h * 0.06)
        title = title_font.render(f"联机大厅 · {self.mode_label}", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(g.w // 2, title_y)))

        title_bottom = title_y + title.get_height()

        if self.is_host and self.net is not None:
            addr = f"{self.net.lan_ip}:{self.net.port}"
            pub = self.net.public_ip
            if pub:
                host_line = f"房主地址:  {addr}    公网:  {pub}:{self.net.port}"
            else:
                host_line = f"房主地址:  {addr}    （公网 IP 获取中...）"
            addr_surf = sub_font.render(host_line, True, GREEN)
            addr_y = title_bottom + 8
            self.screen.blit(addr_surf, addr_surf.get_rect(center=(g.w // 2, addr_y)))
            title_bottom = addr_y + addr_surf.get_height()

        if self.is_host:
            connected = sum(1 for p in self.players if p.get("connected", True))
            sub_text = f"房间 {self.room_id}    {connected}/{self.max_players} 人已连接"
            sub = sub_font.render(sub_text, True, GRAY_MUTE)
            sub_y = title_bottom + 6
            self.screen.blit(sub, sub.get_rect(center=(g.w // 2, sub_y)))
            title_bottom = sub_y + sub.get_height()

        self._title_bottom = title_bottom + 18

        self._draw_player_slots()

        me_idx = next((i for i, p in enumerate(self.players) if p["is_me"]), 0)
        if me_idx < len(self.players):
            ready_text = "✅ 已准备" if self.players[me_idx]["ready"] else "⏳ 未准备"
            self.btn_ready.color = (46, 204, 113) if self.players[me_idx]["ready"] else (241, 196, 15)
            self.btn_ready.text = ready_text

        can_start_now = self.is_host and self.can_start()
        self.btn_start.color = (46, 204, 113) if can_start_now else (75, 80, 110)
        self.btn_start.text = "开始游戏" if self.is_host else "等待房主开始..."

        for b in [self.btn_back, self.btn_ready, self.btn_start]:
            b.update(mouse_pos)
            b.draw(self.screen)

        if self.is_host and self.net is not None:
            accepted = len(self._accepted_peer_indices)
            waiting = self.max_players - 1 - accepted
            if waiting > 0 and self.net._accept_running:
                tip_font = _load_font(int(_clamp(14 * g.s, 9, 20)))
                tip = tip_font.render(f"等待 {waiting} 位玩家加入... （已连接 {accepted}/{self.max_players - 1}）", True, (241, 196, 15))
                self.screen.blit(tip, tip.get_rect(center=(g.w // 2, g.h - g.edge_pad - self.btn_start.rect.h - 40)))

    def _draw_player_slots(self) -> None:
        g = self._g
        n = self.max_players
        gap = int(_clamp(g.w * 0.025, 10, 28))
        available = g.w - g.edge_pad * 2 - gap * (n - 1)
        slot_w = available // n
        slot_h = int(_clamp(g.h * 0.45, 260, 420))
        min_slot_y = int(g.h * 0.17)
        if hasattr(self, '_title_bottom'):
            slot_y = max(min_slot_y, self._title_bottom)
        else:
            slot_y = min_slot_y

        teams = _assign_teams(n, self.mode)

        for i in range(n):
            sx = g.edge_pad + i * (slot_w + gap)
            slot_rect = Rect(sx, slot_y, slot_w, slot_h)
            pygame.draw.rect(self.screen, (52, 73, 94), slot_rect, border_radius=12)
            pygame.draw.rect(self.screen, (75, 80, 110), slot_rect, 2, border_radius=12)

            if i < len(self.players):
                p = self.players[i]
                team_id = teams[i]
                team_c = _team_color(team_id, self.mode)
                avatar_r = int(_clamp(slot_w * 0.32, 36, 72))
                avatar_cx = sx + slot_w // 2
                avatar_cy = slot_y + int(slot_h * 0.30)
                is_online = p.get("connected", True)
                is_ready = p.get("ready", False)

                if is_online:
                    pygame.draw.circle(self.screen, team_c, (avatar_cx, avatar_cy), avatar_r)
                    pygame.draw.circle(self.screen, WHITE, (avatar_cx, avatar_cy), avatar_r, 2)
                    label_font = _load_font(max(12, int(avatar_r * 0.55)))
                    team_label_num = str(team_id + 1) if self.mode in ("1v1", "2v2") else chr(65 + i)
                    label = label_font.render(team_label_num, True, WHITE)
                    self.screen.blit(label, label.get_rect(center=(avatar_cx, avatar_cy)))
                else:
                    pygame.draw.circle(self.screen, (80, 80, 90), (avatar_cx, avatar_cy), avatar_r)
                    pygame.draw.circle(self.screen, (120, 120, 130), (avatar_cx, avatar_cy), avatar_r, 2)
                    q_font = _load_font(max(14, int(avatar_r * 0.7)))
                    q = q_font.render("×", True, (200, 80, 80))
                    self.screen.blit(q, q.get_rect(center=(avatar_cx, avatar_cy)))

                name_font = _load_font(max(13, int(slot_w * 0.11)))
                name_color = WHITE if p["is_me"] else (180, 185, 205)
                name_surf = name_font.render(p["name"], True, name_color)
                if name_surf.get_width() > slot_w - 20:
                    name_surf = pygame.transform.smoothscale(
                        name_surf, (slot_w - 20, name_surf.get_height()))
                self.screen.blit(name_surf, name_surf.get_rect(
                    center=(avatar_cx, avatar_cy + avatar_r + name_font.get_height() // 2 + 8)))

                if self.mode in ("1v1", "2v2"):
                    team_label = "绿队" if team_id == 0 else "红队"
                else:
                    team_label = f"FFA-{chr(65 + team_id)}"
                team_font = _load_font(max(10, int(slot_w * 0.08)))
                team_surf = team_font.render(team_label, True, team_c)
                self.screen.blit(team_surf, team_surf.get_rect(
                    center=(avatar_cx, avatar_cy + avatar_r + name_font.get_height() + team_font.get_height() // 2 + 14)))

                ready_font = _load_font(max(11, int(slot_w * 0.09)))
                if is_ready or p["is_me"]:
                    ready_color = (46, 204, 113)
                    ready_text_str = "✅ 已准备"
                else:
                    ready_color = (141, 153, 174)
                    ready_text_str = "⏳ 等待中"
                ready_surf = ready_font.render(ready_text_str, True, ready_color)
                self.screen.blit(ready_surf, ready_surf.get_rect(
                    center=(avatar_cx, slot_y + slot_h - int(slot_h * 0.15))))

                if p["is_me"]:
                    me_tag = _load_font(max(9, int(slot_w * 0.07))).render("(我)", True, WHITE)
                    self.screen.blit(me_tag, me_tag.get_rect(topright=(sx + slot_w - 10, slot_y + 8)))
                if self.is_host and i == 0 and p["is_me"]:
                    host_tag = _load_font(max(9, int(slot_w * 0.07))).render("房主", True, (241, 196, 15))
                    self.screen.blit(host_tag, host_tag.get_rect(topleft=(sx + 10, slot_y + 8)))
            else:
                avatar_r = int(_clamp(slot_w * 0.32, 36, 72))
                avatar_cx = sx + slot_w // 2
                avatar_cy = slot_y + int(slot_h * 0.30)
                pygame.draw.circle(self.screen, (60, 62, 78), (avatar_cx, avatar_cy), avatar_r)
                pygame.draw.circle(self.screen, (90, 92, 110), (avatar_cx, avatar_cy), avatar_r, 2)
                empty_font = _load_font(max(11, int(slot_w * 0.09)))
                empty = empty_font.render("等待加入...", True, (110, 112, 130))
                self.screen.blit(empty, empty.get_rect(
                    center=(avatar_cx, avatar_cy + avatar_r + empty_font.get_height())))


# ══════ 主游戏界面（轮流单人视角）═════
class Game:
    def __init__(self, engine: "GameEngine", training_mode: bool = False) -> None:
        self.engine = engine
        self.training_mode = training_mode
        self.view_player_index = 0
        self.renderer = GUIRenderer(self)
        engine.renderer = self.renderer

        pygame.init()
        title_suffix = "  [训练营地]" if training_mode else ""
        pygame.display.set_caption("回合计牌游戏" + title_suffix)
        self._g = Geometry(BASE_W, BASE_H)
        self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
        self.clock = pygame.time.Clock()

        self.selected_card_index: Optional[int] = None
        self.card_rects: List[Rect] = []
        self.field_card_rects: List[Rect] = []
        self.log_lines: List[str] = []
        self.error_msg: Optional[str] = None
        self.error_timer: int = 0
        self.hint_msg: Optional[str] = None
        self.hint_timer: int = 0
        self.overlay_text: Optional[str] = None
        self.transition_text: Optional[str] = None
        self.transition_timer: int = 0

        self._last_card_click_idx: Optional[int] = None
        self._last_card_click_time: int = 0
        self._double_click_ms: int = 350

        self._bot_action_timer: int = 0
        self._bot_delay_frames: int = FPS // 2
        self._bot_thinking: bool = False

        self._pending_target_card_idx: Optional[int] = None

        self.ops_panel_open = True
        self._quit_to_menu = False

        self._build_buttons()
        self._layout_cards()

    def _build_buttons(self) -> None:
        g = self._g

        btn_h = int(_clamp(40 * g.s, 30, 54))
        gap = int(_clamp(8 * g.s, 4, 12))
        btn_w = int(_clamp(140 * g.s, 90, 180))

        header_close = int(_clamp(14 * g.s, 12, 22))
        panel_pad = int(_clamp(10 * g.s, 6, 14))
        inner_pad = int(_clamp(8 * g.s, 4, 10))

        f_ops_title = _load_font(int(_clamp(16 * g.s, 12, 22)))
        f_action = _load_font(int(_clamp(18 * g.s, 12, 24)))
        f_exit = _load_font(int(_clamp(14 * g.s, 10, 20)))

        panel_x = g.w - g.edge_pad - (btn_w + panel_pad * 2)
        panel_y = g.top_panel_y + g.player_panel_h + int(g.edge_pad * 0.5)

        if self.training_mode:
            big_h = int(btn_h * 1.3)
            panel_h = header_close + panel_pad * 2 + inner_pad + big_h * 2 + gap * 2 + btn_h
            panel_w = btn_w + panel_pad * 2

            self.ops_panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
            self.ops_close_rect = Rect(
                panel_x + panel_w - panel_pad - header_close,
                panel_y + panel_pad,
                header_close, header_close,
            )

            inner_x = panel_x + panel_pad
            inner_y = panel_y + panel_pad + header_close + inner_pad

            self.btn_play = Button(
                Rect(inner_x, inner_y, btn_w, big_h),
                "打牌", RED, font=_load_font(int(_clamp(22 * g.s, 14, 30))),
            )
            self.btn_next_turn = Button(
                Rect(inner_x, inner_y + big_h + gap, btn_w, big_h),
                "下回合", GREEN, font=_load_font(int(_clamp(22 * g.s, 14, 30))),
            )
            self.btn_main_menu = Button(
                Rect(inner_x, inner_y + (big_h + gap) * 2, btn_w, btn_h),
                "退出主菜单", (108, 117, 125), font=f_exit,
            )
            self._ops_title_font = f_ops_title
            return

        panel_w = btn_w + panel_pad * 2
        panel_h = header_close + panel_pad * 2 + inner_pad + btn_h * 4 + gap * 3

        self.ops_panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
        self.ops_close_rect = Rect(
            panel_x + panel_w - panel_pad - header_close,
            panel_y + panel_pad,
            header_close, header_close,
        )

        inner_x = panel_x + panel_pad
        inner_y = panel_y + panel_pad + header_close + inner_pad

        self.btn_end = Button(
            Rect(inner_x, inner_y, btn_w, btn_h),
            "结束回合", GREEN, font=f_action,
        )
        self.btn_play = Button(
            Rect(inner_x, inner_y + btn_h + gap, btn_w, btn_h),
            "出牌", RED, font=f_action,
        )
        self.btn_peace = Button(
            Rect(inner_x, inner_y + (btn_h + gap) * 2, btn_w, btn_h),
            "求和", (131, 102, 255), font=f_action,
        )
        self.btn_surrender = Button(
            Rect(inner_x, inner_y + (btn_h + gap) * 3, btn_w, btn_h),
            "投降", (108, 117, 125), font=f_action,
        )
        self._ops_title_font = f_ops_title

    def _current_hand(self) -> List["Card"]:
        return self.engine.players[self.view_player_index].hand

    def _layout_cards(self) -> None:
        g = self._g
        self.card_rects.clear()
        self.field_card_rects.clear()

        field_cards = self.engine.state.field_cards
        hand = self._current_hand()

        play_top = g.top_panel_y + g.player_panel_h + int(g.edge_pad * 0.5)
        play_bottom = g.h - g.footer_h - g.edge_pad

        usable_left = g.center_area_x
        usable_right = g.center_area_x + g.center_area_w
        if self.ops_panel_open and hasattr(self, "ops_panel_rect"):
            usable_right = min(usable_right, self.ops_panel_rect.x - g.edge_pad)
        usable_w = max(usable_right - usable_left, 100)

        center_x = usable_left
        center_w = usable_w

        field_top = play_top + 4
        field_h_available = (play_bottom - play_top) * 0.28

        total_field = len(field_cards)
        total_hand = len(hand)

        if total_field > 0:
            field_card_h = max(30, int(min(field_h_available, play_bottom - play_top - 120)))
            field_card_w = max(25, int(field_card_h * g.card_ratio))
            field_gap = max(4, int(g.card_gap * 0.6))

            total_field_w = total_field * field_card_w + (total_field - 1) * field_gap
            if total_field_w > center_w:
                scale = center_w / total_field_w
                field_card_w = max(20, int(field_card_w * scale))
                field_card_h = int(field_card_w / g.card_ratio)
                total_field_w = total_field * field_card_w + (total_field - 1) * field_gap

            field_start_x = center_x + (center_w - total_field_w) // 2
            field_y = field_top

            for i in range(total_field):
                fx = field_start_x + i * (field_card_w + field_gap)
                self.field_card_rects.append(Rect(fx, field_y, field_card_w, field_card_h))

        if total_hand == 0:
            return

        hand_scale = 0.72
        hand_card_w = max(36, int(g.card_w * hand_scale))
        hand_card_h = max(52, int(hand_card_w / g.card_ratio))
        hand_gap = max(3, int(g.card_gap * 0.7))

        total_hand_w = total_hand * hand_card_w + (total_hand - 1) * hand_gap
        if total_hand_w > center_w - g.edge_pad:
            hand_gap = max(1, int((center_w - g.edge_pad - total_hand * hand_card_w) / max(1, total_hand - 1)))
            hand_gap = max(1, hand_gap)
            total_hand_w = total_hand * hand_card_w + (total_hand - 1) * hand_gap
            if total_hand_w > center_w - g.edge_pad:
                scale = (center_w - g.edge_pad) / total_hand_w
                hand_card_w = max(24, int(hand_card_w * scale))
                hand_card_h = max(36, int(hand_card_w / g.card_ratio))
                total_hand_w = total_hand * hand_card_w + (total_hand - 1) * hand_gap

        hand_start_x = center_x + (center_w - total_hand_w) // 2
        hand_y = play_bottom - hand_card_h

        for i in range(total_hand):
            hx = hand_start_x + i * (hand_card_w + hand_gap)
            self.card_rects.append(Rect(hx, hand_y, hand_card_w, hand_card_h))

    def log(self, msg: str) -> None:
        self.log_lines.append(msg)
        if len(self.log_lines) > 200:
            self.log_lines.pop(0)

    def _first_opponent_index(self) -> int:
        vi = self.view_player_index
        my_tid = getattr(self.engine.players[vi], "team_id", -1)
        for i in range(len(self.engine.players)):
            if i == vi:
                continue
            if getattr(self.engine.players[i], "team_id", -1) == my_tid:
                continue
            return i
        return -1

    def _find_clicked_opponent(self, pos: Tuple[int, int]) -> Optional[int]:
        vi = self.view_player_index
        my_tid = getattr(self.engine.players[vi], "team_id", -1)
        if not hasattr(self, "_player_panel_rects"):
            return None
        for i, rect in enumerate(self._player_panel_rects):
            if i == vi:
                continue
            if getattr(self.engine.players[i], "team_id", -1) == my_tid:
                continue
            if rect.collidepoint(pos):
                return i
        return None

    def _find_clicked_teammate(self, pos: Tuple[int, int]) -> Optional[int]:
        vi = self.view_player_index
        my_tid = getattr(self.engine.players[vi], "team_id", -1)
        engine_mode = getattr(self.engine, "mode", "1v1")
        if engine_mode not in ("1v1", "2v2"):
            return None
        if not hasattr(self, "_player_panel_rects"):
            return None
        for i, rect in enumerate(self._player_panel_rects):
            if i == vi:
                continue
            if getattr(self.engine.players[i], "team_id", -1) == my_tid:
                if rect.collidepoint(pos):
                    return i
        return None

    def flash_error(self, msg: str) -> None:
        self.error_msg = msg
        self.error_timer = FPS * 3

    def flash_hint(self, msg: str) -> None:
        self.hint_msg = msg
        self.hint_timer = FPS * 3

    def _resolve_target_index(self, card: "Card") -> Optional[int]:
        if not card.needs_target():
            return None
        if len(self.engine.players) <= 2:
            return self._first_opponent_index()
        opp_idx = self._find_clicked_opponent(pygame.mouse.get_pos())
        if opp_idx is not None:
            return opp_idx
        return ...

    def show_game_over_overlay(self, winner: str) -> None:
        self.overlay_text = f"胜者 {winner}"

    def show_transition(self, text: str, duration_frames: int = FPS) -> None:
        self.transition_text = text
        self.transition_timer = duration_frames

    def _handle_click(self, pos: Tuple[int, int]) -> None:
        if self.engine.state.is_game_over:
            return

        if hasattr(self, 'ops_close_rect') and self.ops_close_rect.collidepoint(pos):
            self.ops_panel_open = False
            return

        if self._pending_target_card_idx is not None:
            target_idx = self._find_clicked_opponent(pos)
            if target_idx is not None:
                hand_idx = self._pending_target_card_idx
                self._pending_target_card_idx = None
                self.selected_card_index = None
                ok = self.engine.play_card(hand_idx, target_idx)
                if ok:
                    self._layout_cards()
                return
            if self._find_clicked_teammate(pos) is not None:
                self.flash_error("不能对队友使用这张卡！请选择敌方玩家")
                return
            self._pending_target_card_idx = None

        if hasattr(self, 'ops_toggle_rect') and self.ops_toggle_rect.collidepoint(pos):
            self.ops_panel_open = True
            return

        if self.ops_panel_open:
            if self.training_mode:
                if hasattr(self, 'btn_main_menu') and self.btn_main_menu.is_clicked(pos, True):
                    self._quit_to_menu = True
                    return

                if hasattr(self, 'btn_next_turn') and self.btn_next_turn.is_clicked(pos, True):
                    self.selected_card_index = None
                    self._pending_target_card_idx = None
                    self._manual_next_turn_training()
                    return

                if self.engine.state.current_player_index != self.view_player_index:
                    return

                if self.btn_play.is_clicked(pos, True):
                    if self.selected_card_index is None:
                        self.flash_error("请先点选一张手牌")
                        return
                    card = self._current_hand()[self.selected_card_index]
                    target_index = self._resolve_target_index(card)
                    if target_index is ...:
                        self.flash_error("请点击要选择的对手")
                        return
                    ok = self.engine.play_card(self.selected_card_index, target_index)
                    if ok:
                        self.selected_card_index = None
                        self._pending_target_card_idx = None
                        self._layout_cards()
                    return
            else:
                peace_proposer = self.engine.state.peace_proposer_index
                if peace_proposer is not None and peace_proposer != self.view_player_index:
                    if self.btn_peace.is_clicked(pos, True):
                        self.engine.accept_peace(self.view_player_index)
                        return

                if self.btn_peace.is_clicked(pos, True):
                    self.engine.propose_peace(self.view_player_index)
                    return

                if self.btn_surrender.is_clicked(pos, True):
                    self.engine.surrender(self.view_player_index)
                    return

                if self.engine.state.current_player_index != self.view_player_index:
                    return

                if self.btn_end.is_clicked(pos, True):
                    self.selected_card_index = None
                    self._pending_target_card_idx = None
                    self.engine.end_turn()
                    self._trigger_transition()
                    self._layout_cards()
                    return

                if self.btn_play.is_clicked(pos, True):
                    if self.selected_card_index is None:
                        self.flash_error("请先点选一张手牌")
                        return
                    card = self._current_hand()[self.selected_card_index]
                    target_index = self._resolve_target_index(card)
                    if target_index is ...:
                        self.flash_error("请点击要选择的对手")
                        return
                    ok = self.engine.play_card(self.selected_card_index, target_index)
                    if ok:
                        self.selected_card_index = None
                        self._pending_target_card_idx = None
                        self._layout_cards()
                    return

        for i, rect in enumerate(self.card_rects):
            if rect.collidepoint(pos):
                now = pygame.time.get_ticks()
                is_double = (self._last_card_click_idx == i
                            and now - self._last_card_click_time < self._double_click_ms)
                self._last_card_click_idx = i
                self._last_card_click_time = now

                if is_double and self.engine.state.current_player_index == self.view_player_index:
                    card = self._current_hand()[i]
                    if card.needs_target() and len(self.engine.players) > 2:
                        self._pending_target_card_idx = i
                        self.selected_card_index = i
                        self.flash_hint("请点击对手以选择目标")
                        return
                    target_index = self._first_opponent_index() if card.needs_target() else None
                    ok = self.engine.play_card(i, target_index)
                    if ok:
                        self.selected_card_index = None
                        self._pending_target_card_idx = None
                        self._layout_cards()
                elif self.selected_card_index == i:
                    self.selected_card_index = None
                    self._pending_target_card_idx = None
                else:
                    self.selected_card_index = i
                    card = self._current_hand()[i]
                    if card.needs_target() and len(self.engine.players) > 2:
                        self._pending_target_card_idx = i
                        self.flash_hint("请点击对手以选择目标，再点一次「出牌」")
                    else:
                        self._pending_target_card_idx = None
                return

    def _auto_end_turn_training(self) -> None:
        self.engine.end_turn()
        self.engine.start_turn()
        self.engine.end_turn()
        self.engine.start_turn()

    def _run_training_bot(self) -> None:
        pass

    def _manual_next_turn_training(self) -> None:
        self.engine.end_turn()
        self.engine.start_turn()
        self.engine.end_turn()
        self.engine.start_turn()
        self._trigger_transition()
        self._layout_cards()

    def _resolve_turn_label(self, cur_index: Optional[int] = None) -> str:
        if cur_index is None:
            cur_index = self.engine.state.current_player_index
        vi = self.view_player_index
        engine_mode = getattr(self.engine, "mode", "1v1")
        my_tid = getattr(self.engine.players[vi], "team_id", -1) if 0 <= vi < len(self.engine.players) else -1
        cur_tid = getattr(self.engine.players[cur_index], "team_id", -1) if 0 <= cur_index < len(self.engine.players) else -1
        if cur_index == vi:
            return "你的回合"
        elif engine_mode in ("1v1", "2v2") and my_tid == cur_tid:
            return "队友回合"
        else:
            return "对手回合"

    def _trigger_transition(self) -> None:
        self.show_transition(self._resolve_turn_label(), duration_frames=FPS)
        self._layout_cards()
    # ════ 绘制 ════

    def _draw_bg(self) -> None:
        self.screen.fill(BG_DARK)

    def _draw_header(self, rtt_ms: float = -1.0) -> None:
        g = self._g
        pygame.draw.rect(self.screen, BG_PANEL, (0, 0, g.w, g.header_h))
        pygame.draw.rect(self.screen, (60, 65, 90),
                         (0, g.header_h - 1, g.w, 1))

        turn_str = self._resolve_turn_label()

        peace_proposer = self.engine.state.peace_proposer_index
        if peace_proposer is not None:
            if peace_proposer == self.view_player_index:
                peace_note = " · 求和等待中"
            else:
                peace_note = " · 同意求和"
        else:
            peace_note = ""

        info_text = (
            f"第 {self.engine.state.turn_count} 回合 · {turn_str}"
            f"{peace_note} · 牌库 {len(self.engine.shared_deck)}/{self.engine.deck_total_size}"
        )

        title_text = "回合计牌游戏"
        if self.training_mode:
            title_text = "训练营地  ·  回合计牌游戏"
        title = g.font_title.render(title_text, True,
                                    (241, 196, 15) if self.training_mode else WHITE)
        info = g.font_sub.render(info_text, True, GRAY_MUTE)

        y_start = max(2, (g.header_h - title.get_height() - 4 - info.get_height()) // 2)
        title_x = (g.w - title.get_width()) // 2
        info_x = (g.w - info.get_width()) // 2
        self.screen.blit(title, (title_x, y_start))
        self.screen.blit(info, (info_x, y_start + title.get_height() + 4))

        if rtt_ms >= 0:
            self._draw_signal_icon(rtt_ms, g)

    def _draw_side_panels(self) -> None:
        g = self._g
        players = self.engine.players
        n = len(players)
        gap = g.player_panel_gap
        total_gap = gap * (n - 1)
        avail = g.w - g.edge_pad * 2 - total_gap
        panel_w = avail // n
        panel_h = g.player_panel_h
        panel_y = g.top_panel_y

        self._player_panel_rects: List[Rect] = []
        for i, p in enumerate(players):
            px = g.edge_pad + i * (panel_w + gap)
            rect = Rect(px, panel_y, panel_w, panel_h)
            self._player_panel_rects.append(rect)
            is_me = (i == self.view_player_index)
            self._draw_one_panel(px, panel_y, panel_w, panel_h, p, is_me)

    def _draw_one_panel(self, x: int, y: int, w: int, h: int,
                         player: "Player", is_me: bool) -> None:
        engine_mode = getattr(self.engine, "mode", "1v1")
        tid = getattr(player, "team_id", 0)
        vi = self.view_player_index
        my_tid = getattr(self.engine.players[vi], "team_id", -1) if 0 <= vi < len(self.engine.players) else -1
        is_friendly = (my_tid == tid)

        if engine_mode in ("1v1", "2v2"):
            if is_friendly:
                avatar_color = (52, 211, 153)
                team_label = "🟢 队友" if not is_me else "🟢 己方"
            else:
                avatar_color = (239, 35, 60)
                team_label = "🔴 敌方"
            badge_text = str(tid + 1)
        elif engine_mode == "4p_free":
            avatar_color = FFA_COLORS[tid % len(FFA_COLORS)]
            team_label = f"FFA-{chr(65 + tid)}"
            badge_text = chr(65 + tid)
        else:
            avatar_color = GREEN
            team_label = ""
            badge_text = ""

        border_color = avatar_color
        if is_me and self.engine.state.current_player_index == self.view_player_index:
            border_w = 3
        else:
            border_w = 2 if is_friendly else 1

        pygame.draw.rect(self.screen, BG_PANEL, (x, y, w, h), border_radius=8)
        pygame.draw.rect(self.screen, border_color, (x, y, w, h), border_w, border_radius=8)

        pad = max(6, int(h * 0.10))
        row_h = (h - pad * 2) // 3
        row1_y = y + pad
        row2_y = row1_y + row_h
        row3_y = row2_y + row_h

        dot_r = max(7, int(h * 0.16))
        dot_cx = x + pad + dot_r
        dot_cy = row1_y + row_h // 2
        pygame.draw.circle(self.screen, avatar_color, (dot_cx, dot_cy), dot_r)
        pygame.draw.circle(self.screen, (255, 255, 255), (dot_cx, dot_cy), dot_r, 1)
        if badge_text:
            badge_font = _load_font(max(10, int(dot_r * 0.8)))
            badge_surf = badge_font.render(badge_text, True, WHITE)
            self.screen.blit(badge_surf, badge_surf.get_rect(center=(dot_cx, dot_cy)))

        name_color = (255, 255, 255) if is_me else (170, 175, 200)
        name_font = _load_font(max(11, int(h * 0.20)))
        name_surf = name_font.render(player.name, True, name_color)
        max_name_w = int(w * 0.38)
        if name_surf.get_width() > max_name_w:
            name_surf = pygame.transform.smoothscale(
                name_surf, (max_name_w, name_surf.get_height()))
        self.screen.blit(name_surf, (dot_cx + dot_r + 4, row1_y + (row_h - name_surf.get_height()) // 2))

        if team_label:
            tag_font = _load_font(max(8, int(h * 0.12)))
            tag_surf = tag_font.render(team_label, True, avatar_color)
            tag_x = dot_cx + dot_r + 4 + name_surf.get_width() + 3
            tag_y = row1_y + (row_h - tag_surf.get_height()) // 2
            self.screen.blit(tag_surf, (tag_x, tag_y))

        hp_color = (231, 76, 60) if not player.is_alive() else (200, 210, 220)
        hp_font = _load_font(max(11, int(h * 0.20)))
        hp_text = f"生命 {player.health}/{player.max_health}"
        hp_surf = hp_font.render(hp_text, True, hp_color)
        hp_x = x + w - pad - hp_surf.get_width()
        self.screen.blit(hp_surf, (hp_x, row1_y + (row_h - hp_surf.get_height()) // 2))

        bar_h = max(6, int(row_h * 0.45))
        bar_y = row2_y + (row_h - bar_h) // 2
        bar_x = x + pad
        bar_w = w - pad * 2
        ratio = max(0.0, player.health / max(1, player.max_health))
        pygame.draw.rect(self.screen, (60, 40, 40),
                         (bar_x, bar_y, bar_w, bar_h),
                         border_radius=max(2, bar_h // 3))
        fill_w = int(bar_w * ratio)
        if fill_w > 0:
            if ratio > 0.5:
                c = (46, 204, 113)
            elif ratio > 0.25:
                c = (241, 196, 15)
            else:
                c = (231, 76, 60)
            pygame.draw.rect(self.screen, c,
                             (bar_x, bar_y, fill_w, bar_h),
                             border_radius=max(2, bar_h // 3))
        pygame.draw.rect(self.screen, (100, 100, 100),
                         (bar_x, bar_y, bar_w, bar_h), 1,
                         border_radius=max(2, bar_h // 3))

        cell_w = (w - pad * 2) // 3
        info_font = _load_font(max(9, int(h * 0.16)))
        info_h = info_font.get_height()
        info_cy = row3_y + (row_h - info_h) // 2

        score_color = (241, 196, 15) if is_me else (180, 150, 60)
        score_surf = info_font.render(f"{player.score}/{player.max_score}", True, score_color)
        self.screen.blit(score_surf, (x + pad + (cell_w - score_surf.get_width()) // 2, info_cy))

        hand_surf = info_font.render(f"{len(player.hand)}", True, GRAY_MUTE)
        self.screen.blit(hand_surf, (x + pad + cell_w + (cell_w - hand_surf.get_width()) // 2, info_cy))

        discard_surf = info_font.render(f"弃{len(player.discard)}", True, GRAY_MUTE)
        self.screen.blit(discard_surf, (x + pad + cell_w * 2 + (cell_w - discard_surf.get_width()) // 2, info_cy))

    def _rtt_total_width(self, g: "Geometry") -> int:
        bar_w = 5
        bar_gap = 3
        bars_w = 4 * bar_w + 3 * bar_gap
        rtt_font_h = g.font_small.get_height()
        rtt_text_w = g.font_small.size("---ms")[0]
        return bars_w + 8 + rtt_text_w

    def _draw_signal_icon(self, rtt_ms: float, g: "Geometry",
                           align_y: int = -1) -> None:
        bar_w = 5
        bar_gap = 3
        bar_hs = [6, 10, 14, 18]
        bars_w = len(bar_hs) * bar_w + (len(bar_hs) - 1) * bar_gap
        rtt_text_w = g.font_small.size(f"{int(rtt_ms)}ms")[0]
        total_w = bars_w + 8 + rtt_text_w
        base_x = g.w - g.edge_pad - total_w

        max_bar_h = bar_hs[-1]
        text_h = g.font_small.get_height()
        cell_h = max(max_bar_h, text_h)

        if align_y < 0:
            base_y = (g.header_h - cell_h) // 2
        else:
            base_y = align_y

        if rtt_ms < 100:
            color = (46, 204, 113)
            active = 4
        elif rtt_ms < 250:
            color = (241, 196, 15)
            active = 3
        elif rtt_ms < 500:
            color = (230, 126, 34)
            active = 2
        else:
            color = (231, 76, 60)
            active = 1

        text_top = base_y + (cell_h - text_h) // 2
        rtt_text = g.font_small.render(f"{int(rtt_ms)}ms", True, color)
        self.screen.blit(rtt_text, (base_x, text_top))

        bar_group_w = bars_w
        bar_group_x = base_x + rtt_text_w + 8
        bar_top = base_y + (cell_h - max_bar_h) // 2

        for i, h in enumerate(bar_hs):
            bx = bar_group_x + i * (bar_w + bar_gap)
            by = bar_top + (max_bar_h - h)
            c = color if i < active else (60, 65, 75)
            pygame.draw.rect(self.screen, c, (bx, by, bar_w, h), border_radius=1)

    def _draw_player_panel(self, x: int, player: "Player",
                           is_current: bool, is_viewer: bool,
                           hide_cards: bool = False) -> None:
        g = self._g
        pw = int(g.player_panel_h * 2.5)
        panel_pad = int(_clamp(pw * 0.08, 8, 20))
        panel_w = pw - panel_pad * 2
        panel_top = g.header_h
        panel_bottom = g.h - g.footer_h
        panel_h = panel_bottom - panel_top
        rect = Rect(x, panel_top, pw, panel_h)

        if hide_cards:
            color = BG_PANEL
        elif is_current and is_viewer:
            color = RED
        elif is_viewer:
            color = (58, 80, 100)
        else:
            color = BG_PANEL

        pygame.draw.rect(self.screen, color, rect, border_radius=8)

        tag = ""
        if hide_cards:
            tag = "[对手]"
        elif is_viewer:
            tag = "[己方]"
        elif is_current:
            tag = "[回合中]"

        content_x = x + panel_pad
        cur_y = panel_top + panel_pad

        name = g.font_info.render(f"{tag} {player.name}", True, WHITE)
        self.screen.blit(name, (content_x, cur_y))
        cur_y += name.get_height() + panel_pad

        if hide_cards:
            for icon, val in [
                ("生命", f"{player.health}/{player.max_health}"),
                ("手牌背面", str(len(player.hand))),
                ("弃牌", str(len(player.discard))),
            ]:
                line = g.font_small.render(f"{icon}  {val}", True, WHITE)
                self.screen.blit(line, (content_x, cur_y))
                cur_y += g.line_h

            back_total_w = len(player.hand) * g.back_w + (max(0, len(player.hand) - 1)) * g.back_gap
            start_bx = x + (pw - back_total_w) // 2
            back_y = cur_y + int(panel_pad * 0.8)
            for i in range(len(player.hand)):
                back_rect = Rect(
                    start_bx + i * (g.back_w + g.back_gap),
                    back_y, g.back_w, g.back_h,
                )
                pygame.draw.rect(self.screen, CARD_BACK_CLR, back_rect, border_radius=4)
                pygame.draw.rect(
                    self.screen, CARD_BACK_INNER,
                    Rect(back_rect.x + 4, back_rect.y + 4,
                         g.back_w - 8, g.back_h - 8),
                    border_radius=3,
                )
        else:
            for icon, val in [
                ("生命", f"{player.health}/{player.max_health}"),
                ("积分", f"{player.score}/{player.max_score}"),
                ("弃牌", str(len(player.discard))),
                ("手牌", str(len(player.hand))),
            ]:
                line = g.font_small.render(f"{icon}  {val}", True, WHITE)
                self.screen.blit(line, (content_x, cur_y))
                cur_y += g.line_h

    def _draw_card(self, rect: Rect, card: "Card", index: int,
                    dimmed: bool = False) -> None:
        g = self._g
        base_color = CARD_COLOR_MAP.get(card.template_color, (245, 245, 245))
        if dimmed:
            color = tuple(int(c * 0.6) for c in base_color)
            outline_color = (120, 120, 120)
        else:
            color = base_color
            outline_color = RED if self.selected_card_index == index else GRAY_MUTE
        outline_w = 3 if (self.selected_card_index == index and not dimmed) else 1

        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        pygame.draw.rect(self.screen, outline_color, rect, outline_w, border_radius=10)

        pad = max(6, int(rect.w * 0.045))
        inner_x = rect.x + pad
        inner_w = rect.w - pad * 2

        type_colors = {"攻击": RED, "恢复": GREEN, "功能": PURPLE, "积分": (191, 148, 0)}
        type_color = type_colors.get(card.card_type, DARK)
        if dimmed:
            type_color = tuple(int(c * 0.55) for c in type_color)

        circle_r = max(10, int(rect.w * 0.14))
        circle_cx = rect.x + pad + circle_r
        circle_cy = rect.y + pad + circle_r
        affordable = card.cost <= self.engine.players[self.view_player_index].score
        circle_fill = RED if (not affordable and not dimmed) else (40, 40, 55)
        pygame.draw.circle(self.screen, circle_fill, (circle_cx, circle_cy), circle_r)
        pygame.draw.circle(self.screen, (120, 120, 140), (circle_cx, circle_cy), circle_r, 1)
        cost_font = _load_font(max(9, int(rect.w * 0.125)))
        cost_txt = cost_font.render(f"⬡{card.cost}", True, WHITE)
        self.screen.blit(cost_txt, cost_txt.get_rect(center=(circle_cx, circle_cy)))

        header_font_size = max(12, int(rect.w * 0.16))
        header_font = _load_font(header_font_size)
        header_line_h = header_font_size + 2

        col_x = circle_cx + circle_r + pad
        col_w = rect.x + rect.w - pad - col_x

        name_surf = header_font.render(card.name, True, (20, 20, 30))
        if name_surf.get_width() > col_w:
            name_surf = pygame.transform.smoothscale(
                name_surf, (col_w, name_surf.get_height()))
        name_y = rect.y + pad
        self.screen.blit(name_surf, (col_x, name_y))

        type_font_size = max(9, int(rect.w * 0.10))
        type_font = _load_font(type_font_size)
        type_surf = type_font.render(f"[{card.card_type}]", True, type_color)
        type_y = name_y + header_line_h + 2
        self.screen.blit(type_surf, (col_x, type_y))

        header_bottom = type_y + type_surf.get_height() + pad
        header_bottom = max(header_bottom, rect.y + pad + circle_r * 2 + pad)

        divider_y = header_bottom
        pygame.draw.line(self.screen, (80, 80, 100),
                         (rect.x + pad, divider_y), (rect.x + rect.w - pad, divider_y), 1)

        body_top = divider_y + pad
        body_bottom = rect.y + rect.h - pad
        body_h = body_bottom - body_top

        desc_text = card.description.strip() if card.description else ""
        flavor_text = card.flavor.strip() if card.flavor else ""

        has_desc = bool(desc_text)
        has_flavor = bool(flavor_text)

        flavor_h = 0
        desc_h = body_h
        gap_between = 0
        if has_desc and has_flavor:
            flavor_h = max(20, int(body_h * 0.32))
            gap_between = max(4, int(rect.w * 0.02))
            desc_h = body_h - flavor_h - gap_between
        elif has_flavor:
            flavor_h = body_h

        def wrap_text_full(text: str, font: pygame.font.Font, max_w: int) -> list:
            if not text:
                return []
            lines: list = []
            cur = ""
            for ch in text:
                test = cur + ch
                if font.size(test)[0] > max_w and cur:
                    lines.append(cur)
                    cur = ch
                else:
                    cur = test
            if cur:
                lines.append(cur)
            return lines

        if has_desc and desc_h > 8:
            desc_font_size = max(10, int(rect.w * 0.11))
            desc_font = _load_font(desc_font_size)
            desc_line_h = desc_font_size + max(1, int(rect.w * 0.008))
            desc_lines = wrap_text_full(desc_text, desc_font, inner_w)

            total_desc_text_h = len(desc_lines) * desc_line_h
            desc_bg_rect = Rect(inner_x, body_top, inner_w,
                                min(desc_h, total_desc_text_h + pad // 2))
            bg_surface = pygame.Surface((desc_bg_rect.w, desc_bg_rect.h), pygame.SRCALPHA)
            bg_alpha = 120 if not dimmed else 60
            bg_surface.fill((255, 255, 255, bg_alpha))
            self.screen.blit(bg_surface, desc_bg_rect.topleft)

            text_color = (25, 25, 35) if not dimmed else (80, 80, 95)
            for i, line in enumerate(desc_lines):
                line_surf = desc_font.render(line, True, text_color)
                self._blit_center(line_surf, rect.centerx,
                                  body_top + i * desc_line_h + desc_line_h // 2)

        if has_flavor and flavor_h > 6:
            flavor_top = body_top + desc_h + gap_between if has_desc else body_top
            flavor_font_size = max(9, int(rect.w * 0.095))
            flavor_font = _load_font(flavor_font_size, italic=True)
            flavor_line_h = flavor_font_size + max(1, int(rect.w * 0.006))
            flavor_lines = wrap_text_full(flavor_text, flavor_font, inner_w)

            total_flavor_text_h = len(flavor_lines) * flavor_line_h
            flavor_bg_rect = Rect(inner_x, flavor_top, inner_w,
                                  min(flavor_h, total_flavor_text_h + pad // 2))
            bg_surface = pygame.Surface((flavor_bg_rect.w, flavor_bg_rect.h), pygame.SRCALPHA)
            bg_alpha = 75 if not dimmed else 38
            bg_surface.fill((60, 60, 70, bg_alpha))
            self.screen.blit(bg_surface, flavor_bg_rect.topleft)

            flavor_color = (85, 85, 100) if not dimmed else (130, 130, 145)
            for i, line in enumerate(flavor_lines):
                line_surf = flavor_font.render(line, True, flavor_color)
                self._blit_center(line_surf, rect.centerx,
                                  flavor_top + i * flavor_line_h + flavor_line_h // 2)

    def _blit_center(self, surf: pygame.Surface, cx: int, cy: int) -> None:
        self.screen.blit(surf, surf.get_rect(center=(cx, cy)))

    def _draw_cards(self) -> None:
        g = self._g
        field_cards = self.engine.state.field_cards
        if field_cards and self.field_card_rects:
            for i, rect in enumerate(self.field_card_rects):
                if i < len(field_cards):
                    card = Card.from_dict(field_cards[i])
                    self._draw_card(rect, card, -1, dimmed=True)

        hand = self._current_hand()
        for i, rect in enumerate(self.card_rects):
            if i < len(hand):
                self._draw_card(rect, hand[i], i)
        if not hand and not field_cards:
            name = self.engine.players[self.view_player_index].name
            txt = g.font_sub.render(f"{name} 手牌为空", True, GRAY_MUTE)
            play_top = g.top_panel_y + g.player_panel_h + int(g.edge_pad * 0.5)
            play_bottom = g.h - g.footer_h - g.edge_pad
            self._blit_center(txt, g.w // 2, (play_top + play_bottom) // 2)

    def _draw_log(self) -> None:
        g = self._g
        log_top = g.h - g.footer_h + int(g.footer_h * 0.44)
        log_h = g.footer_h - int(g.footer_h * 0.52)
        log_rect = Rect(0, log_top, g.w, log_h)
        pygame.draw.rect(self.screen, BG_ACCENT, log_rect)

        header = g.font_small.render("事件日志", True, GRAY_MUTE)
        self.screen.blit(header, (g.edge_pad, log_top - int(g.line_h * 0.9)))

        visible = self.log_lines[-int(log_h / g.line_h) + 1:] if self.log_lines else []
        ty = log_top + int(g.line_h * 0.2)
        for line in visible:
            surf = g.font_small.render(line, True, WHITE)
            self.screen.blit(surf, (g.edge_pad + 5, ty))
            ty += g.line_h

    def _draw_buttons(self, mouse_pos: Tuple[int, int]) -> None:
        g = self._g
        can_act = (self.engine.state.current_player_index == self.view_player_index)

        if self.ops_panel_open:
            pr = self.ops_panel_rect
            pygame.draw.rect(self.screen, BG_PANEL, pr, border_radius=10)
            pygame.draw.rect(self.screen, (75, 80, 110), pr, 1, border_radius=10)

            title = self._ops_title_font.render(
                "训练模式" if self.training_mode else "操作", True, WHITE
            )
            self.screen.blit(title, (pr.x + 10, pr.y + 6))

            cr = self.ops_close_rect
            pygame.draw.rect(self.screen, (80, 85, 110), cr, border_radius=4)
            close_font = _load_font(max(10, cr.h - 6))
            close_txt = close_font.render("X", True, (231, 76, 60))
            self._blit_center(close_txt, cr.centerx, cr.centery)

            if self.training_mode:
                self.btn_play.update(mouse_pos if can_act else (-1, -1))
                if not can_act:
                    pygame.draw.rect(self.screen, BG_ACCENT, self.btn_play.rect, border_radius=6)
                    pygame.draw.rect(self.screen, GRAY_MUTE, self.btn_play.rect, 1, border_radius=6)
                    txt = self.btn_play.font.render(self.btn_play.text, True, GRAY_MUTE)
                    self.screen.blit(txt, txt.get_rect(center=self.btn_play.rect.center))
                else:
                    self.btn_play.draw(self.screen)
                if hasattr(self, 'btn_next_turn'):
                    self.btn_next_turn.update(mouse_pos)
                    self.btn_next_turn.draw(self.screen)
                self.btn_main_menu.update(mouse_pos)
                self.btn_main_menu.draw(self.screen)
            else:
                for b in [self.btn_end, self.btn_play]:
                    b.update(mouse_pos if can_act else (-1, -1))
                    if not can_act:
                        pygame.draw.rect(self.screen, BG_ACCENT, b.rect, border_radius=6)
                        pygame.draw.rect(self.screen, GRAY_MUTE, b.rect, 1, border_radius=6)
                        txt = b.font.render(b.text, True, GRAY_MUTE)
                        self.screen.blit(txt, txt.get_rect(center=b.rect.center))
                    else:
                        b.draw(self.screen)

                peace_proposer = self.engine.state.peace_proposer_index
                if peace_proposer is None:
                    self.btn_peace.text = "求和"
                    self.btn_peace.color = (131, 102, 255)
                    self.btn_peace.update(mouse_pos)
                    self.btn_peace.draw(self.screen)
                elif peace_proposer != self.view_player_index:
                    self.btn_peace.text = "同意求和"
                    self.btn_peace.color = GREEN
                    self.btn_peace.update(mouse_pos)
                    self.btn_peace.draw(self.screen)
                else:
                    pygame.draw.rect(self.screen, BG_ACCENT, self.btn_peace.rect, border_radius=6)
                    pygame.draw.rect(self.screen, GRAY_MUTE, self.btn_peace.rect, 1, border_radius=6)
                    txt = self.btn_peace.font.render("等待中..", True, GRAY_MUTE)
                    self.screen.blit(txt, txt.get_rect(center=self.btn_peace.rect.center))

                self.btn_surrender.update(mouse_pos)
                self.btn_surrender.draw(self.screen)

        else:
            tw = int(_clamp(80 * g.s, 56, 110))
            th = int(_clamp(28 * g.s, 22, 40))
            toggle_x = g.w - g.edge_pad - tw
            toggle_y = g.top_panel_y + g.player_panel_h + int(g.edge_pad * 0.5)
            self.ops_toggle_rect = Rect(toggle_x, toggle_y, tw, th)

            pygame.draw.rect(self.screen, BG_PANEL, self.ops_toggle_rect, border_radius=6)
            pygame.draw.rect(self.screen, (75, 80, 110), self.ops_toggle_rect, 1, border_radius=6)
            toggle_font = _load_font(int(_clamp(14 * g.s, 10, 20)))
            toggle_txt = "训练模式 " if self.training_mode else "操作 "
            txt = toggle_font.render(toggle_txt, True, WHITE)
            self._blit_center(txt, self.ops_toggle_rect.centerx, self.ops_toggle_rect.centery)

    def _draw_error(self) -> None:
        if self.error_msg and self.error_timer > 0:
            g = self._g
            bw = int(_clamp(400 * g.s, 260, 540))
            bh = int(_clamp(80 * g.s, 50, 110))
            box_rect = Rect(g.w // 2 - bw // 2, g.h // 2 - bh // 2, bw, bh)
            pygame.draw.rect(self.screen, RED, box_rect, border_radius=10)
            txt = g.font_info.render(self.error_msg, True, WHITE)
            self._blit_center(txt, box_rect.centerx, box_rect.centery)
            self.error_timer -= 1

    def _draw_hint(self) -> None:
        if self.hint_msg and self.hint_timer > 0:
            g = self._g
            bw = int(_clamp(400 * g.s, 260, 540))
            bh = int(_clamp(80 * g.s, 50, 110))
            x = g.w // 2 - bw // 2
            y = g.top_panel_y + g.player_panel_h + int(g.edge_pad * 0.3)
            box_rect = Rect(x, y, bw, bh)
            pygame.draw.rect(self.screen, (46, 125, 194), box_rect, border_radius=10)
            txt = g.font_info.render(self.hint_msg, True, WHITE)
            self._blit_center(txt, box_rect.centerx, box_rect.centery)
            self.hint_timer -= 1

    def _draw_overlay(self) -> None:
        if not self.overlay_text:
            return
        g = self._g
        overlay = pygame.Surface((g.w, g.h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        big_font = _load_font(int(_clamp(48 * g.s, 26, 72)))
        title = big_font.render("游戏结束", True, WHITE)
        self._blit_center(title, g.w // 2, g.h // 2 - int(g.h * 0.06))

        sub = g.font_title.render(self.overlay_text, True, RED)
        self._blit_center(sub, g.w // 2, g.h // 2 + int(g.h * 0.02))

        tip = g.font_sub.render("点击窗口关闭", True, GRAY_MUTE)
        self._blit_center(tip, g.w // 2, g.h // 2 + int(g.h * 0.10))

    def _draw_transition(self) -> None:
        if not self.transition_text or self.transition_timer <= 0:
            return
        g = self._g
        txt = g.font_big.render(self.transition_text, True, WHITE)
        self._blit_center(txt, g.w // 2, g.h // 2)
        self.transition_timer -= 1

    # ════ 主循环 ════

    def run(self) -> None:
        self.engine.renderer.render_intro(self.engine)
        self.engine.start_turn()
        self._layout_cards()

        self.view_player_index = self.engine.state.current_player_index
        self.show_transition(self._resolve_turn_label(), duration_frames=FPS)

        self._game_over_clicked = False

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode(
                        (self._g.w, self._g.h), RESIZABLE
                    )
                    self._build_buttons()
                    self._layout_cards()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
                    if self.engine.state.is_game_over and not self._game_over_clicked:
                        self._game_over_clicked = True
                        return

            if mouse_click:
                self._handle_click(mouse_pos)

            if self._quit_to_menu:
                return

            if self.training_mode:
                self._run_training_bot()

            self._draw_bg()
            self._draw_header()
            self._draw_side_panels()
            self._draw_cards()
            self._draw_buttons(mouse_pos)
            self._draw_error()
            self._draw_hint()
            self._draw_transition()
            self._draw_overlay()

            pygame.display.flip()
            self.clock.tick(FPS)


# ══════ 联机辅助函数 ══════
def _broadcast_state_multi(net: Network, engine: "GameEngine", game: "Game",
                            num_clients: int) -> None:
    for client_idx in range(num_clients):
        viewer_index = client_idx + 1
        snapshot = engine.snapshot(viewer_index=viewer_index, log_tail=game.log_lines[-30:])
        try:
            net.send_to(client_idx, Message("STATE", snapshot))
        except ConnectionError:
            pass


def _broadcast_state(net: Network, engine: "GameEngine", game: "Game", viewer_index: int) -> None:
    snapshot = engine.snapshot(viewer_index=viewer_index, log_tail=game.log_lines[-30:])
    try:
        net.send(Message("STATE", snapshot))
    except ConnectionError:
        pass


def _apply_action(
    engine: "GameEngine", game: "Game", action: str, payload: dict, actor_index: int
) -> tuple:
    saved_renderer = engine.renderer
    engine.renderer = None
    success = True
    error_msg = None
    try:
        if action == "play_card":
            idx = payload.get("hand_index")
            target = payload.get("target_index")
            if idx is not None:
                ok = engine.play_card(idx, target)
                if not ok:
                    p = engine.current_player
                    card = p.hand[idx] if 0 <= idx < len(p.hand) else None
                    if card is None:
                        error_msg = "无效的手牌索引"
                    elif p.score < card.get_actual_cost(p, engine):
                        cost = card.get_actual_cost(p, engine)
                        error_msg = f"积分不足！需要 {cost} 积分，当前只有 {p.score}"
                    elif card.needs_target() and target is None:
                        error_msg = "这张卡需要选择目标"
                    else:
                        error_msg = "出牌失败"
                    success = False
                else:
                    game._layout_cards()
        elif action == "end_turn":
            game.selected_card_index = None
            engine.end_turn()
            game._layout_cards()
        elif action == "surrender":
            engine.surrender(actor_index)
        elif action == "propose_peace":
            engine.propose_peace(actor_index)
        elif action == "accept_peace":
            engine.accept_peace(actor_index)
    finally:
        engine.renderer = saved_renderer
    return success, error_msg


def _mode_to_deck_scale(mode: str) -> float:
    if mode == "1v1":
        return 0.5
    return 1.0


def run_host_multiplayer(net: Network, player_names: List[str],
                         host_player_index: int = 0,
                         is_training_dummy: bool = False,
                         mode: str = "4p_free") -> None:
    from .engine import GameEngine
    deck_scale = _mode_to_deck_scale(mode)
    engine = GameEngine(player_names, deck_scale=deck_scale, mode=mode)
    if is_training_dummy:
        for i, p in enumerate(engine.players):
            if i != host_player_index:
                p.score = 0
                p.hand.clear()
                p.training_dummy = True

    game = Game(engine, training_mode=is_training_dummy)
    game.view_player_index = host_player_index

    num_clients = len(player_names) - 1

    try:
        for client_idx in range(num_clients):
            net.send_to(client_idx, Message("START", {
                "client_index": client_idx + 1,
                "player_names": [p.name for p in engine.players],
            }))
    except ConnectionError:
        pygame.quit()
        sys.exit(1)

    game.engine.renderer.render_intro(game.engine)
    game.engine.start_turn()
    game._layout_cards()
    game.show_transition(game._resolve_turn_label(), duration_frames=FPS)
    game._game_over_clicked = False

    _broadcast_state_multi(net, engine, game, num_clients)

    while True:
        game.view_player_index = host_player_index
        mouse_pos = pygame.mouse.get_pos()
        mouse_click = False

        for event in pygame.event.get():
            if event.type == QUIT:
                net.close()
                pygame.quit()
                sys.exit(0)
            elif event.type == VIDEORESIZE:
                game._g = Geometry(event.w, event.h)
                game.screen = pygame.display.set_mode((game._g.w, game._g.h), RESIZABLE)
                game._build_buttons()
                game._layout_cards()
            elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                mouse_click = True
                if engine.state.is_game_over and not game._game_over_clicked:
                    game._game_over_clicked = True
                    net.close()
                    return

        if mouse_click:
            game._handle_click(mouse_pos)
            _broadcast_state_multi(net, engine, game, num_clients)

        remote_acted = False
        for client_idx in range(num_clients):
            if not net.is_peer_alive(client_idx):
                engine.surrender(client_idx + 1)
                game.log(f"{player_names[client_idx+1]} 已断开，判定投降")
                continue
            for msg in net.poll_peer(client_idx):
                if msg.type == "ACTION":
                    actor_index = client_idx + 1
                    success, error_msg = _apply_action(engine, game, msg.payload["action"],
                                                       msg.payload.get("data", {}), actor_index=actor_index)
                    if success:
                        remote_acted = True
                    else:
                        try:
                            net.send_to(client_idx, Message("ERROR", error_msg))
                        except ConnectionError:
                            pass
                elif msg.type == "DISCONNECT":
                    engine.surrender(client_idx + 1)
                    game.log(f"{player_names[client_idx+1]} 已断开连接")

        if remote_acted:
            _broadcast_state_multi(net, engine, game, num_clients)

        game._draw_bg()
        game._draw_header(rtt_ms=net.last_rtt_ms)
        game._draw_side_panels()
        game._draw_cards()
        game._draw_buttons(mouse_pos)
        game._draw_error()
        game._draw_hint()
        game._draw_transition()
        game._draw_overlay()

        pygame.display.flip()
        game.clock.tick(FPS)


def run_host(net: Network) -> None:
    from .engine import GameEngine
    engine = GameEngine(["房主", "对手"], deck_scale=0.5)
    game = Game(engine)
    game.view_player_index = 0

    try:
        net.send(Message("START", {
            "client_index": 1,
            "player_names": [p.name for p in engine.players],
        }))
    except ConnectionError:
        pygame.quit()
        sys.exit(1)

    game.engine.renderer.render_intro(game.engine)
    game.engine.start_turn()
    game._layout_cards()
    game.show_transition(game._resolve_turn_label(), duration_frames=FPS)
    game._game_over_clicked = False

    _broadcast_state(net, engine, game, viewer_index=1)

    while True:
        game.view_player_index = 0
        mouse_pos = pygame.mouse.get_pos()
        mouse_click = False

        for event in pygame.event.get():
            if event.type == QUIT:
                net.close()
                pygame.quit()
                sys.exit(0)
            elif event.type == VIDEORESIZE:
                game._g = Geometry(event.w, event.h)
                game.screen = pygame.display.set_mode((game._g.w, game._g.h), RESIZABLE)
                game._build_buttons()
                game._layout_cards()
            elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                mouse_click = True
                if engine.state.is_game_over and not game._game_over_clicked:
                    game._game_over_clicked = True
                    net.close()
                    return

        if mouse_click:
            game._handle_click(mouse_pos)
            _broadcast_state(net, engine, game, viewer_index=1)

        remote_acted = False
        for msg in net.recv_all():
            if msg.type == "ACTION":
                success, error_msg = _apply_action(engine, game, msg.payload["action"],
                                                   msg.payload.get("data", {}), actor_index=1)
                if success:
                    remote_acted = True
                else:
                    try:
                        net.send(Message("ERROR", error_msg))
                    except ConnectionError:
                        pass
            elif msg.type == "DISCONNECT":
                game.log("对手已断开连接")
                engine.surrender(1)
                break
        if remote_acted:
            _broadcast_state(net, engine, game, viewer_index=1)

        if not net.is_alive and not engine.state.is_game_over:
            game.log("连接断开，对手退出")
            engine.surrender(1)
            _broadcast_state(net, engine, game, viewer_index=1)

        game._draw_bg()
        game._draw_header(rtt_ms=net.last_rtt_ms)
        game._draw_side_panels()
        game._draw_cards()
        game._draw_buttons(mouse_pos)
        game._draw_error()
        game._draw_hint()
        game._draw_transition()
        game._draw_overlay()

        pygame.display.flip()
        game.clock.tick(FPS)


# ══════ Client 端游戏循环 ══════
class ClientGame(Game):
    def __init__(self, net: Network, client_index: int, player_names: list) -> None:
        from .engine import GameEngine, GameState
        self.net = net
        self.client_index = client_index
        engine = GameEngine(player_names)
        engine.state = GameState()
        for p in engine.players:
            p.hand.clear()
        super().__init__(engine)
        pygame.display.set_caption(f"回合计牌游戏  ·  {player_names[client_index]}")
        self.transition_text = None
        self.transition_timer = 0
        self._game_over_clicked = False
        self._pending_target_card_idx: Optional[int] = None

    @property
    def view_player_index(self) -> int:
        return self.client_index

    @view_player_index.setter
    def view_player_index(self, _v: int) -> None:
        pass

    def _current_hand(self) -> list:
        return self.engine.players[self.client_index].hand

    def log(self, msg: str) -> None:
        self.log_lines.append(msg)
        if len(self.log_lines) > 200:
            self.log_lines.pop(0)

    def _send_action(self, action: str, data: Optional[dict] = None) -> None:
        try:
            self.net.send(Message("ACTION", {"action": action, "data": data or {}}))
        except ConnectionError:
            self.flash_error("连接已断开")

    def _first_opponent_index(self) -> int:
        ci = self.client_index
        my_tid = getattr(self.engine.players[ci], "team_id", -1)
        for i in range(len(self.engine.players)):
            if i == ci:
                continue
            if getattr(self.engine.players[i], "team_id", -1) == my_tid:
                continue
            return i
        return -1

    def _find_clicked_opponent(self, pos: Tuple[int, int]) -> Optional[int]:
        ci = self.client_index
        my_tid = getattr(self.engine.players[ci], "team_id", -1)
        if not hasattr(self, "_player_panel_rects"):
            return None
        for i, rect in enumerate(self._player_panel_rects):
            if i == ci:
                continue
            if getattr(self.engine.players[i], "team_id", -1) == my_tid:
                continue
            if rect.collidepoint(pos):
                return i
        return None

    def _find_clicked_teammate(self, pos: Tuple[int, int]) -> Optional[int]:
        ci = self.client_index
        my_tid = getattr(self.engine.players[ci], "team_id", -1)
        engine_mode = getattr(self.engine, "mode", "1v1")
        if engine_mode not in ("1v1", "2v2"):
            return None
        if not hasattr(self, "_player_panel_rects"):
            return None
        for i, rect in enumerate(self._player_panel_rects):
            if i == ci:
                continue
            if getattr(self.engine.players[i], "team_id", -1) == my_tid:
                if rect.collidepoint(pos):
                    return i
        return None

    def _handle_click(self, pos: Tuple[int, int]) -> None:
        if self.engine.state.is_game_over:
            return

        peace_proposer = self.engine.state.peace_proposer_index
        if peace_proposer is not None and peace_proposer != self.client_index:
            if self.btn_peace.is_clicked(pos, True):
                self._send_action("accept_peace")
                return

        if self.btn_peace.is_clicked(pos, True):
            self._send_action("propose_peace")
            return

        if self.btn_surrender.is_clicked(pos, True):
            self._send_action("surrender")
            return

        if self.engine.state.current_player_index != self.client_index:
            return

        if self._pending_target_card_idx is not None:
            target_idx = self._find_clicked_opponent(pos)
            if target_idx is not None:
                hand_idx = self._pending_target_card_idx
                self._pending_target_card_idx = None
                self.selected_card_index = None
                self._send_action("play_card", {
                    "hand_index": hand_idx,
                    "target_index": target_idx,
                })
                return
            if self._find_clicked_teammate(pos) is not None:
                self.flash_error("不能对队友使用这张卡！请选择敌方玩家")
                return
            self._pending_target_card_idx = None

        if self.btn_end.is_clicked(pos, True):
            self.selected_card_index = None
            self._pending_target_card_idx = None
            self._send_action("end_turn")
            return

        if self.btn_play.is_clicked(pos, True):
            if self.selected_card_index is None:
                self.flash_error("请先点选一张手牌")
                return
            card = self._current_hand()[self.selected_card_index]
            target_index = None
            if card.needs_target():
                opp_idx = self._find_clicked_opponent(pos)
                if opp_idx is None:
                    opp_idx = self._first_opponent_index()
                target_index = opp_idx if opp_idx >= 0 else None
            self.selected_card_index = None
            self._send_action("play_card", {
                "hand_index": self.selected_card_index if target_index is None else (self._pending_target_card_idx or 0),
                "target_index": target_index,
            })
            return

        for i, rect in enumerate(self.card_rects):
            if rect.collidepoint(pos):
                now = pygame.time.get_ticks()
                is_double = (self._last_card_click_idx == i
                            and now - self._last_card_click_time < self._double_click_ms)
                self._last_card_click_idx = i
                self._last_card_click_time = now

                card = self._current_hand()[i]
                if is_double:
                    target_index = None
                    if card.needs_target():
                        opp_idx = self._first_opponent_index()
                        target_index = opp_idx if opp_idx >= 0 else None
                    self._send_action("play_card", {
                        "hand_index": i,
                        "target_index": target_index,
                    })
                elif self.selected_card_index == i:
                    self.selected_card_index = None
                    self._pending_target_card_idx = None
                else:
                    self.selected_card_index = i
                    if card.needs_target():
                        self._pending_target_card_idx = i
                    else:
                        self._pending_target_card_idx = None
                return

    def _apply_state(self, data: dict) -> None:
        self.engine.apply_remote_state(data)
        if "log_tail" in data and data["log_tail"]:
            self.log_lines = list(data["log_tail"])
        self._layout_cards()
        if self.engine.state.is_game_over and self.overlay_text is None:
            winner = self.engine.state.winner or "平局"
            self.overlay_text = f"胜者 {winner}"

    def run(self) -> None:
        waiting_first_state = True
        conn_lost = False

        while True:
            mouse_pos = pygame.mouse.get_pos()
            mouse_click = False

            for event in pygame.event.get():
                if event.type == QUIT:
                    try:
                        self.net.send(Message("DISCONNECT", None))
                    except ConnectionError:
                        pass
                    self.net.close()
                    pygame.quit()
                    sys.exit(0)
                elif event.type == VIDEORESIZE:
                    self._g = Geometry(event.w, event.h)
                    self.screen = pygame.display.set_mode((self._g.w, self._g.h), RESIZABLE)
                    self._build_buttons()
                    self._layout_cards()
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mouse_click = True
                    if self.engine.state.is_game_over and not self._game_over_clicked:
                        self._game_over_clicked = True
                        self.net.close()
                        return

            for msg in self.net.recv_all():
                if msg.type == "STATE":
                    self._apply_state(msg.payload)
                    waiting_first_state = False
                elif msg.type == "ERROR":
                    self.flash_error(msg.payload)
                elif msg.type == "DISCONNECT":
                    self.log("房主已断开连接")
                    conn_lost = True

            if conn_lost and not self.engine.state.is_game_over:
                self.overlay_text = "连接断开"
                self.engine.state.is_game_over = True

            if mouse_click:
                self._handle_click(mouse_pos)

            self._draw_bg()
            opp_index = 1 - self.client_index
            opp = self.engine.players[opp_index]
            me = self.engine.players[self.client_index]
            g = self._g

            self._draw_header(rtt_ms=self.net.last_rtt_ms)
            self._draw_side_panels()
            self._draw_cards()
            self._draw_buttons(mouse_pos)
            self._draw_error()
            self._draw_hint()
            self._draw_overlay()

            if waiting_first_state:
                wait_surf = g.font_big.render("等待房主推送初始状态..", True, GRAY_MUTE)
                Game._blit_center(self, wait_surf, g.w // 2, g.h // 2)

            if not self.net.is_alive and not self.engine.state.is_game_over and not conn_lost:
                self.flash_error("连接已断开")
                conn_lost = True

            pygame.display.flip()
            self.clock.tick(FPS)


def run_client(net: Network) -> None:
    client_index = -1
    player_names = []

    deadline = time.time() + 10.0
    while time.time() < deadline:
        for msg in net.recv_all():
            if msg.type == "START":
                client_index = msg.payload["client_index"]
                player_names = msg.payload["player_names"]
                break
        if client_index >= 0:
            break
        pygame.time.wait(50)

    if client_index < 0:
        print("未收到 START 消息")
        net.close()
        pygame.quit()
        sys.exit(1)

    game = ClientGame(net, client_index, player_names)
    game.run()


def run_client_multiplayer(net: Network, payload: dict) -> None:
    client_index = payload["client_index"]
    player_names = payload["player_names"]
    game = ClientGame(net, client_index, player_names)
    game.run()