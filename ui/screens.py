"""主菜单 / 模式选择 / 设置 / 联机大厅等待"""
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
    _load_font, _clamp, _get_clipboard_text, _sanitize_for_render,
    load_settings, save_settings, SETTINGS_PATH, DEFAULT_SETTINGS,
)
from ..network import Network, Message, ConnectionError, DEFAULT_PORT
from ..music import MusicManager, scan_audio_folder, format_track_path
from ..credits import CREDITS

if TYPE_CHECKING:
    from ..engine import GameEngine
    from .gui_base import Geometry
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

        mid_gap = int(max(btn_w * 0.04, 6))
        half_w = (btn_w - mid_gap) // 2

        self.btn_1v1 = Button(
            Rect(cx - btn_w // 2, start_y, half_w, btn_h),
            "单挑模式", RED, font=big_font,
        )
        self.btn_endless = Button(
            Rect(cx - btn_w // 2 + half_w + mid_gap, start_y, half_w, btn_h),
            "永无止境", (30, 30, 60), font=big_font,
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
            elif stage == "soon_endless":
                result = self._loop_net_mode("endless_1v1")
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
        from ..network import Network
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
        from ..network import Network
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
                if self.btn_endless.is_clicked(mouse_pos, True):
                    return "soon_endless"
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

        for b in [self.btn_1v1, self.btn_endless, self.btn_4p, self.btn_2v2, self.btn_training,
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
    if mode in ("1v1", "endless_1v1"):
        return [0, 1]
    elif mode == "2v2":
        return [0, 1, 0, 1, 0, 1][:num_players]
    elif mode == "4p_free":
        return list(range(num_players))
    return [0] * num_players


def _team_color(team_id: int, mode: str) -> tuple:
    if mode in ("1v1", "2v2", "endless_1v1"):
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
