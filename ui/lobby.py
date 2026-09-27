"""联机房间（玩家集结、模式选择、准备状态）"""
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

if TYPE_CHECKING:
    from ..engine import GameEngine
class LobbyScreen:
    def __init__(self, mode: str = "1v1", is_host: bool = True,
                 room_id: str = "", net: Optional["Network"] = None,
                 my_name: str = "", host_address: str = "") -> None:
        from ..network import Network
        self.mode = mode
        self.is_host = is_host
        self.room_id = room_id or "AUTO"
        self.net: Optional[Network] = net
        self.my_name = my_name or ("房主" if is_host else "房客")
        self.host_address = host_address

        self.mode_caps = {
            "1v1":         ("单挑", 2),
            "endless_1v1": ("永无止境", 2),
            "2v2":         ("双人组队对抗", 4),
            "4p_free":     ("四人混战", 4),
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
