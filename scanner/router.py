from __future__ import annotations

import logging

from scanner.svc_commands import parse_svc, SvcMode, SvcUser
from modes.base import Mode

log = logging.getLogger("scanner.router")


class Router:
    def __init__(self) -> None:
        pass

    def route(self, session: "ScannerSession", line: str) -> None:
        cmd = parse_svc(line)
        if cmd is not None:
            if isinstance(cmd, SvcUser):
                session.set_user(cmd.user_id, reason="svc")
                return
            if isinstance(cmd, SvcMode):
                session.set_mode(cmd.mode, reason="svc")
                return
        if session.get_user_id() is None:
            session.tts.say("Сначала выберите пользователя")
            return
        # обычный payload -> текущий режим
        mode: Mode = session.get_mode_handler()
        mode.on_scan(session=session, payload=line)
        session.touch_activity()
