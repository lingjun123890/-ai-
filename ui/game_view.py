"""核心对战视图：Game（单机/同屏轮流）+ ClientGame（联机客户端）"""
import sys
import os
import time
import json
from typing import Optional, List, Tuple, Any, TYPE_CHECKING

import pygame
from pygame.locals import *

from .gui_base import (
    Geometry, Button, GUIRenderer,
    BASE_W, BASE_H, MIN_W, MIN_H, FPS,
    BG_DARK, BG_PANEL, BG_ACCENT, WHITE, GRAY_MUTE, RED, GREEN, PURPLE, DARK,
    CARD_BACK_CLR, CARD_BACK_INNER, CARD_COLOR_MAP,
    _load_font, _clamp, _sanitize_for_render,
    load_settings, save_settings,
)
from ..network import Network, Message, ConnectionError, DEFAULT_PORT
from ..card import Card

if TYPE_CHECKING:
    from ..engine import GameEngine
    from ..player import Player
class Game:
    def __init__(self, engine: "GameEngine", training_mode: bool = False,
                 follows_current_view: bool = False) -> None:
        self.engine = engine
        self.training_mode = training_mode
        self.view_player_index = 0
        self.follows_current_view = follows_current_view
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
        panel_h = header_close + panel_pad * 2 + inner_pad + btn_h * 5 + gap * 4

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
        self.btn_main_menu = Button(
            Rect(inner_x, inner_y + (btn_h + gap) * 4, btn_w, btn_h),
            "退出主菜单", (108, 117, 125), font=f_exit,
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
            viewer_alive = self.engine.players[self.view_player_index].is_alive()
            game_over = self.engine.state.is_game_over

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
                viewer_alive = self.engine.players[self.view_player_index].is_alive()
                game_over = self.engine.state.is_game_over

                if self.btn_main_menu.is_clicked(pos, True):
                    if not viewer_alive or game_over:
                        self._quit_to_menu = True
                    return

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
        if self.follows_current_view:
            self.view_player_index = self.engine.state.current_player_index
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
        viewer_dead = not self.engine.players[self.view_player_index].is_alive()
        game_over = self.engine.state.is_game_over

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
                can_quit = viewer_dead or game_over
                self.btn_main_menu.update(mouse_pos if can_quit else (-1, -1))
                self.btn_main_menu.draw(self.screen)

                if not viewer_dead and not game_over:
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
    if mode in ("1v1", "endless_1v1"):
        return 0.5
    return 1.0


def run_host_multiplayer(net: Network, player_names: List[str],
                         host_player_index: int = 0,
                         is_training_dummy: bool = False,
                         mode: str = "4p_free") -> None:
    from ..engine import GameEngine
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
    from ..engine import GameEngine
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
        from ..engine import GameEngine, GameState
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