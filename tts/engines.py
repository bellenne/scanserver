from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("tts.engines")


class TTSEngine:
    def speak(self, text: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        # optional
        return


@dataclass(frozen=True)
class EdgeTTSConfig:
    voice: str
    cache_dir: Path
    cache_enabled: bool = True
    rate: str = "+35%"


class _AsyncLoopThread:
    """Один event loop в отдельном потоке, чтобы не делать asyncio.run() на каждый speak()."""
    def __init__(self) -> None:
        self._loop_ready = threading.Event()
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run, name="edge-tts-loop", daemon=True)
        self._thread.start()
        self._loop_ready.wait()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        loop.run_forever()
        # cleanup
        pending = asyncio.all_tasks(loop)
        for t in pending:
            t.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()

    def submit(self, coro: asyncio.coroutines) -> None:
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        # блокируемся до готовности синтеза — всё равно у нас TTS очередь, наложений не будет
        fut.result()

    def stop(self) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)


class EdgeTTSEngine(TTSEngine):
    """
    edge-tts -> кэш mp3 -> проигрывание через pygame
    Важно: синтез идёт через постоянный asyncio loop, без asyncio.run() на каждую фразу.
    """
    def __init__(self, cfg: EdgeTTSConfig) -> None:
        self.cfg = cfg

        import edge_tts  # type: ignore
        import pygame  # type: ignore

        self._edge_tts = edge_tts
        self._pygame = pygame

        # mixer init once
        if not self._pygame.mixer.get_init():
            self._pygame.mixer.init()

        self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)

        self._loop_thread = _AsyncLoopThread()
        self._gen_lock = threading.Lock()  # чтобы два speak() не синтезировали один и тот же файл параллельно

    def close(self) -> None:
        try:
            self._loop_thread.stop()
        except Exception:
            pass

    def speak(self, text: str) -> None:
        t = text.strip()
        if not t:
            return

        # 1) вычисляем ключ кэша
        cache_path = self._cache_path(t)

        # 2) если есть в кэше — сразу играем
        if self.cfg.cache_enabled and cache_path.exists():
            self._play_mp3(cache_path)
            return

        # 3) иначе синтезим и кладём в кэш (или во временный файл, если кэш отключён)
        with self._gen_lock:
            # повторная проверка (пока ждали lock, мог уже появиться файл)
            if self.cfg.cache_enabled and cache_path.exists():
                self._play_mp3(cache_path)
                return

            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(tmp_fd)
            tmp_file = Path(tmp_path)

            try:
                async def _synth():
                    communicate = self._edge_tts.Communicate(text=t, voice=self.cfg.voice, rate=self.cfg.rate)
                    await communicate.save(str(tmp_file))

                self._loop_thread.submit(_synth())

                if self.cfg.cache_enabled:
                    # атомарно переносим в кэш
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.replace(str(tmp_file), str(cache_path))
                    except Exception:
                        # если replace не удался — просто копируем
                        shutil.copyfile(str(tmp_file), str(cache_path))
                        try:
                            tmp_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                    self._play_mp3(cache_path)
                else:
                    self._play_mp3(tmp_file)

            finally:
                # если кэш выключен — удалим tmp после проигрывания (play_mp3 блокирующий)
                if (not self.cfg.cache_enabled) and tmp_file.exists():
                    try:
                        tmp_file.unlink()
                    except Exception:
                        pass

    def _cache_path(self, text: str) -> Path:
        # ключ зависит от voice + rate + text
        h = hashlib.sha1()
        h.update(self.cfg.voice.encode("utf-8"))
        h.update(b"\0")
        h.update(self.cfg.rate.encode("utf-8"))
        h.update(b"\0")
        h.update(text.encode("utf-8"))
        name = h.hexdigest() + ".mp3"
        return self.cfg.cache_dir / name

    def _play_mp3(self, path: Path) -> None:
        self._pygame.mixer.music.load(str(path))
        self._pygame.mixer.music.play()
        while self._pygame.mixer.music.get_busy():
            self._pygame.time.wait(10)  # чаще проверяем

        # гарантированно отпускаем ресурс, чтобы следующий стартовал сразу
        try:
            self._pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            self._pygame.mixer.music.unload()
        except Exception:
            pass


class Pyttsx3Engine(TTSEngine):
    def __init__(self, voice_name: str | None, rate: int, volume: float) -> None:
        import pyttsx3  # type: ignore

        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)

        if voice_name:
            chosen = None
            for v in self._engine.getProperty("voices") or []:
                name = getattr(v, "name", "")
                if voice_name.lower() in str(name).lower():
                    chosen = v.id
                    break
            if chosen:
                self._engine.setProperty("voice", chosen)

    def speak(self, text: str) -> None:
        t = text.strip()
        if not t:
            return
        self._engine.say(t)
        self._engine.runAndWait()


def build_engine(
    prefer_edge: bool,
    edge_voice: str,
    pyttsx3_voice_name: str | None,
    rate: int,
    volume: float,
    cache_dir: str = ".tts_cache",
    cache_enabled: bool = True,
    edge_rate: str = "+35%",
) -> TTSEngine:
    if prefer_edge:
        try:
            return EdgeTTSEngine(
                EdgeTTSConfig(
                    voice=edge_voice,
                    cache_dir=Path(cache_dir),
                    cache_enabled=cache_enabled,
                    rate=edge_rate,
                )
            )
        except Exception as e:
            log.warning("EdgeTTS init failed, fallback to pyttsx3: %s", e)

    return Pyttsx3Engine(voice_name=pyttsx3_voice_name, rate=rate, volume=volume)
