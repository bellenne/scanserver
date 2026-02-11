from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from tts.engines import TTSEngine, build_engine

log = logging.getLogger("tts")


@dataclass(frozen=True)
class SpeakTask:
    text: str


class TTSManager:
    def __init__(
        self,
        prefer_edge: bool,
        edge_voice: str,
        pyttsx3_voice_name: str | None,
        rate: int,
        volume: float,
    ) -> None:
        self._q: "queue.Queue[SpeakTask]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._engine: TTSEngine = build_engine(
            prefer_edge=prefer_edge,
            edge_voice=edge_voice,
            pyttsx3_voice_name=pyttsx3_voice_name,
            rate=rate,
            volume=volume,
            cache_dir=".tts_cache",
            cache_enabled=True,
            edge_rate="+50%",
        )

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._worker, name="tts-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._q.put(SpeakTask(text=""))
        if self._thread:
            self._thread.join(timeout=2.0)

        try:
            close = getattr(self._engine, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    def say(self, text: str) -> None:
        self._q.put(SpeakTask(text=text))

    def _worker(self) -> None:
        while not self._stop.is_set():
            task = self._q.get()
            if self._stop.is_set():
                break
            try:
                if task.text.strip():
                    self._engine.speak(task.text)
            except Exception as e:
                log.warning("TTS speak failed: %s", e)
