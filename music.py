import os
import random
from typing import Optional, List


AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac",
    ".opus", ".mid", ".mod", ".it", ".xm",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".3gp", ".ts", ".rmvb",
}


def is_audio_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in AUDIO_EXTENSIONS and ext not in VIDEO_EXTENSIONS


def scan_audio_folder(folder: str) -> List[str]:
    if not folder or not os.path.isdir(folder):
        return []
    results = []
    for root, dirs, files in os.walk(folder):
        for f in sorted(files):
            fp = os.path.join(root, f)
            if is_audio_file(fp):
                results.append(fp)
    return results


def format_track_path(path: str, max_len: int = 42) -> str:
    name = os.path.basename(path)
    if len(name) > max_len:
        return name[:max_len - 1] + "…"
    return name


class MusicManager:
    _instance: Optional["MusicManager"] = None

    @classmethod
    def get(cls) -> "MusicManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def __init__(self) -> None:
        self._initialized = False
        self._playlist: List[str] = []
        self._current_index: int = -1
        self._volume: float = 0.5
        self._shuffle: bool = False
        self._loop: bool = True
        self._folder: str = ""
        self._playing: bool = False
        self._paused: bool = False
        self._track_finished: bool = False

    def ensure_init(self) -> bool:
        if self._initialized:
            return True
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.set_endevent()
            self._initialized = True
            return True
        except Exception:
            return False

    def load_settings(self, settings: dict) -> None:
        self._volume = float(settings.get("music_volume", 0.5))
        self._folder = settings.get("music_folder", "")
        self._shuffle = bool(settings.get("music_shuffle", False))
        self._loop = bool(settings.get("music_loop", True))
        if self._folder:
            self._playlist = scan_audio_folder(self._folder)
        self._apply_volume()

    def save_to(self, settings: dict) -> None:
        settings["music_volume"] = self._volume
        settings["music_folder"] = self._folder
        settings["music_shuffle"] = self._shuffle
        settings["music_loop"] = self._loop

    def _apply_volume(self) -> None:
        if self._initialized:
            import pygame
            pygame.mixer.music.set_volume(self._volume)

    def scan_folder(self, folder: str) -> int:
        self._folder = folder
        self._playlist = scan_audio_folder(folder)
        self._current_index = -1
        return len(self._playlist)

    def refresh(self) -> int:
        return self.scan_folder(self._folder)

    @property
    def playlist(self) -> List[str]:
        return list(self._playlist)

    @property
    def playlist_count(self) -> int:
        return len(self._playlist)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current_path(self) -> Optional[str]:
        if 0 <= self._current_index < len(self._playlist):
            return self._playlist[self._current_index]
        return None

    @property
    def current_name(self) -> str:
        p = self.current_path
        return format_track_path(p) if p else "(无曲目)"

    @property
    def folder(self) -> str:
        return self._folder

    @folder.setter
    def folder(self, v: str) -> None:
        self._folder = v
        if v:
            self._playlist = scan_audio_folder(v)
            self._current_index = -1

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, v: float) -> None:
        self._volume = max(0.0, min(1.0, v))
        self._apply_volume()

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, v: bool) -> None:
        self._shuffle = v

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, v: bool) -> None:
        self._loop = v

    @property
    def is_playing(self) -> bool:
        if self._initialized:
            import pygame
            return pygame.mixer.music.get_busy() and not self._paused
        return False

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def has_any(self) -> bool:
        return len(self._playlist) > 0

    def play_index(self, idx: int) -> bool:
        if not self.ensure_init():
            return False
        if not self._playlist:
            return False
        idx = max(0, min(idx, len(self._playlist) - 1))
        path = self._playlist[idx]
        try:
            import pygame
            loops = -1 if self._loop else 0
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play(loops=loops)
            self._current_index = idx
            self._playing = True
            self._paused = False
            self._track_finished = False
            return True
        except Exception:
            return False

    def play_next(self) -> bool:
        if not self._playlist:
            return False
        if self._shuffle and len(self._playlist) > 1:
            nxt = random.randrange(len(self._playlist))
            while nxt == self._current_index:
                nxt = random.randrange(len(self._playlist))
        else:
            nxt = self._current_index + 1
            if nxt >= len(self._playlist):
                nxt = 0
        return self.play_index(nxt)

    def play_prev(self) -> bool:
        if not self._playlist:
            return False
        if self._shuffle and len(self._playlist) > 1:
            nxt = random.randrange(len(self._playlist))
            while nxt == self._current_index:
                nxt = random.randrange(len(self._playlist))
        else:
            nxt = self._current_index - 1
            if nxt < 0:
                nxt = len(self._playlist) - 1
        return self.play_index(nxt)

    def play_first(self) -> bool:
        if not self._playlist:
            return False
        start = random.randrange(len(self._playlist)) if self._shuffle else 0
        return self.play_index(start)

    def play_or_pause(self) -> bool:
        if not self._initialized:
            if not self.ensure_init():
                return False
        import pygame
        if self._paused:
            pygame.mixer.music.unpause()
            self._paused = False
            return True
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self._paused = True
            return True
        if self._playlist:
            if self._current_index < 0 or self._current_index >= len(self._playlist):
                return self.play_first()
            return self.play_index(self._current_index)
        return False

    def stop(self) -> None:
        if self._initialized:
            import pygame
            pygame.mixer.music.stop()
        self._playing = False
        self._paused = False

    def handle_endevent(self) -> None:
        if self._loop or self._shuffle or len(self._playlist) > 1:
            self.play_next()