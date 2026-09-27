"""game.ui — GUI 子包"""
from .gui_base import (
    Geometry, Button, GUIRenderer,
    BASE_W, BASE_H, MIN_W, MIN_H, FPS,
    BG_DARK, BG_PANEL, BG_ACCENT, WHITE, GRAY_MUTE, RED, GREEN, PURPLE, DARK,
    CARD_BACK_CLR, CARD_BACK_INNER, CARD_COLOR_MAP,
    _load_font, _clamp, _get_clipboard_text, _sanitize_for_render,
    load_settings, save_settings, SETTINGS_PATH, DEFAULT_SETTINGS,
)
from .screens import ModeScreen
from .lobby import LobbyScreen
from .game_view import (
    Game, ClientGame,
    _mode_to_deck_scale, run_host_multiplayer, run_host,
    run_client, run_client_multiplayer,
)

__all__ = [
    "Geometry", "Button", "GUIRenderer",
    "BASE_W", "BASE_H", "MIN_W", "MIN_H", "FPS",
    "BG_DARK", "BG_PANEL", "BG_ACCENT", "WHITE", "GRAY_MUTE", "RED", "GREEN", "PURPLE", "DARK",
    "CARD_BACK_CLR", "CARD_BACK_INNER", "CARD_COLOR_MAP",
    "_load_font", "_clamp", "_get_clipboard_text", "_sanitize_for_render",
    "load_settings", "save_settings", "SETTINGS_PATH", "DEFAULT_SETTINGS",
    "ModeScreen", "LobbyScreen", "Game", "ClientGame",
    "_mode_to_deck_scale", "run_host_multiplayer", "run_host",
    "run_client", "run_client_multiplayer",
]