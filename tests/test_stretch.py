from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from api.client import ApiClient
from core.config import Endpoints, load_config
from core.state_store import StateStore
from modes.stretch import StretchMode
from scanner.session import ScannerSession


QR = "WALLPAPER|v=1|oi=1|art=DL-001|w=300|h=270|panels=3|kind=striped|code=test"


class StretchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.posts: list[httpx.Request] = []
        self.post_outcomes: list[int | type[httpx.RequestError]] = []
        self.tts = Mock()
        self.spoken_at_post: list[list[str]] = []
        client = httpx.Client(transport=httpx.MockTransport(self.respond))
        with patch("api.client.httpx.Client", return_value=client):
            self.api = ApiClient("https://mes.example.test")
        self.addCleanup(self.api.close)
        self.store = StateStore(self.root / "state.json")
        self.session = self.make_session({"devices": {}})

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            self.assertEqual(request.url.path, "/api/v1/users/8")
            return httpx.Response(200, json={"id": 8, "name": "Test Operator"})
        self.assertEqual(request.method, "POST")
        self.posts.append(request)
        self.spoken_at_post.append(self.spoken())
        outcome = self.post_outcomes.pop(0) if self.post_outcomes else 200
        if isinstance(outcome, type):
            raise outcome("Simulated connection failure", request=request)
        return httpx.Response(outcome, json={"ok": outcome < 400})

    def make_session(self, state: dict) -> ScannerSession:
        session = ScannerSession(
            device_id="TEST01",
            com_port="COM_TEST",
            baudrate=9600,
            api=self.api,
            users_cache=Mock(),
            tts=self.tts,
            state_store=self.store,
            global_state=state,
            endpoints=Endpoints(),
        )
        # Run the actual scan queue without starting COM, idle or TTS threads.
        session._worker_thread.start()
        self.addCleanup(self.stop_worker, session)
        return session

    def stop_worker(self, session: ScannerSession) -> None:
        session.stop()
        session._worker_thread.join(timeout=2.0)
        self.assertFalse(session._worker_thread.is_alive(), "Scan worker failed to stop")

    def wait_for_scans(self, session: ScannerSession) -> None:
        # Queue.join() has no timeout; use its completion condition with a bound.
        with session._scan_q.all_tasks_done:
            completed = session._scan_q.all_tasks_done.wait_for(
                lambda: session._scan_q.unfinished_tasks == 0, timeout=2.0
            )
        self.assertTrue(completed, "Scan worker did not finish queued scans")

    def scan(self, line: str, session: ScannerSession | None = None) -> None:
        session = session or self.session
        session.on_line(line)
        self.wait_for_scans(session)

    def select_stretch(self, *, with_user: bool = True) -> None:
        self.scan("SVC:MODE:STRETCH")
        if with_user:
            self.scan("SVC:USER:8")
        self.tts.reset_mock()

    def spoken(self) -> list[str]:
        return [call.args[0] for call in self.tts.say.call_args_list]

    def assert_no_success(self) -> None:
        self.assertFalse(any("Натяжка выполнена" in text for text in self.spoken()))

    def test_single_scan_posts_cut_then_stretch_with_standard_event_body(self) -> None:
        self.select_stretch()
        self.scan(QR)

        self.assertEqual(
            [request.url.path for request in self.posts],
            ["/api/v1/cut/scan", "/api/v1/stretch/scan"],
        )
        for request in self.posts:
            body = json.loads(request.content)
            timestamp = body.pop("client_ts")
            self.assertIsNotNone(datetime.fromisoformat(timestamp).utcoffset())
            self.assertEqual(body, {
                "payload": QR,
                "action": "done",
                "user_id": 8,
                "device_id": "TEST01",
            })
        self.assertTrue(any("Натяжка выполнена" in text for text in self.spoken()))
        for messages in self.spoken_at_post:
            self.assertFalse(any("Натяжка выполнена" in text for text in messages))

    def test_cut_failure_stops_before_stretch(self) -> None:
        self.select_stretch()
        for failure in (422, 503, httpx.ConnectError, httpx.ReadTimeout):
            with self.subTest(failure=failure):
                self.posts.clear()
                self.tts.reset_mock()
                self.post_outcomes = [failure]
                self.scan(QR)

                self.assertEqual([request.url.path for request in self.posts], ["/api/v1/cut/scan"])
                self.assert_no_success()
                self.assertTrue(self.spoken())

    def test_stretch_failure_reports_partial_completion_without_retry(self) -> None:
        self.select_stretch()
        for failure in (422, 503, httpx.ConnectError, httpx.ReadTimeout):
            with self.subTest(failure=failure):
                self.posts.clear()
                self.tts.reset_mock()
                self.post_outcomes = [200, failure]
                self.scan(QR)

                self.assertEqual(
                    [request.url.path for request in self.posts],
                    ["/api/v1/cut/scan", "/api/v1/stretch/scan"],
                )
                self.assert_no_success()
                self.assertTrue(any("Резка отправлена" in text for text in self.spoken()))

    def test_working_scan_requires_selected_user(self) -> None:
        self.select_stretch(with_user=False)
        self.scan(QR)

        self.assertEqual(self.posts, [])
        self.assertTrue(any("Сначала выберите пользователя" in text for text in self.spoken()))

    def test_direct_mode_handler_also_requires_user(self) -> None:
        StretchMode().on_scan(self.session, QR)

        self.assertEqual(self.posts, [])
        self.assertTrue(any("Сначала выберите пользователя" in text for text in self.spoken()))

    def test_service_qr_selects_and_persists_mode_without_posting_events(self) -> None:
        self.scan("SVC:MODE:STRETCH")

        self.assertEqual(self.session.get_mode_name(), "STRETCH")
        self.assertIsInstance(self.session.get_mode_handler(), StretchMode)
        self.assertEqual(self.store.load()["devices"]["TEST01"]["mode"], "STRETCH")
        self.assertEqual(self.posts, [])
        self.assertTrue(any("Режим Натяжка" in text for text in self.spoken()))

    def test_restart_restores_stretch_but_still_requires_login(self) -> None:
        self.select_stretch()
        restarted = self.make_session(self.store.load())

        self.assertEqual(restarted.get_mode_name(), "STRETCH")
        self.assertIsInstance(restarted.get_mode_handler(), StretchMode)
        self.assertIsNone(restarted.get_user_id())
        self.scan(QR, session=restarted)
        self.assertEqual(self.posts, [])

    def test_mode_uses_configured_endpoints(self) -> None:
        self.select_stretch()
        self.session.endpoints = Endpoints(events="/custom/cut", stretch="/custom/stretch")
        self.scan(QR)

        self.assertEqual(
            [request.url.path for request in self.posts], ["/custom/cut", "/custom/stretch"]
        )

    def test_worker_preserves_scan_order_with_user_and_mode_commands(self) -> None:
        second_qr = QR.replace("code=test", "code=second")
        for line in (
            "SVC:USER:8",
            "SVC:MODE:STRETCH",
            QR,
            second_qr,
            "SVC:USER:8",  # Remove the user after both scans.
            "SVC:MODE:COMPARE",
        ):
            self.session.on_line(line)
        self.wait_for_scans(self.session)

        self.assertEqual(
            [(request.url.path, json.loads(request.content)["payload"]) for request in self.posts],
            [
                ("/api/v1/cut/scan", QR),
                ("/api/v1/stretch/scan", QR),
                ("/api/v1/cut/scan", second_qr),
                ("/api/v1/stretch/scan", second_qr),
            ],
        )
        self.assertTrue(all(json.loads(request.content)["user_id"] == 8 for request in self.posts))
        self.assertIsNone(self.session.get_user_id())
        self.assertEqual(self.session.get_mode_name(), "COMPARE")


class StretchConfigTests(unittest.TestCase):
    def test_old_config_uses_default_stretch_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text('{"endpoints": {"events": "/legacy/cut"}}', encoding="utf-8")
            config = load_config(path)

        self.assertEqual(config.endpoints.events, "/legacy/cut")
        self.assertEqual(config.endpoints.stretch, "/api/v1/stretch/scan")

    def test_stretch_endpoint_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text('{"endpoints": {"stretch": "/custom/stretch"}}', encoding="utf-8")
            config = load_config(path)

        self.assertEqual(config.endpoints.stretch, "/custom/stretch")


if __name__ == "__main__":
    unittest.main()
