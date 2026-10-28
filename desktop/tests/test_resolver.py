from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from playwright.sync_api import Error as BrowserError

from desktop.models import Cancelled, SessionConfig
from desktop.resolver import resolve_work


class _Page:
    def __init__(self, cancel: Event | None = None):
        self.url = "https://www.douyin.com/video/123"
        self.callback = None
        self.cancel = cancel
        self.reloads = 0
        self.closed = False

    def on(self, name, callback):
        self.callback = callback

    def goto(self, *args, **kwargs):
        self.callback(self.response("999"))

    @staticmethod
    def response(identifier):
        return SimpleNamespace(
            url="https://www.douyin.com/aweme/v1/web/aweme/detail/",
            status=200,
            json=lambda: {"aweme_detail": {
                "aweme_id": identifier, "desc": "正确的视频",
                "video": {"play_addr": {"url_list": ["https://example.com/video.mp4"]}},
            }},
        )

    def is_closed(self):
        return self.closed

    def locator(self, selector):
        return SimpleNamespace(count=lambda: 0)

    def wait_for_timeout(self, milliseconds):
        if self.cancel:
            self.cancel.set()
        else:
            self.callback(self.response("123"))

    def reload(self, **kwargs):
        self.reloads += 1
        self.callback(self.response("123"))

    def evaluate(self, expression):
        return "test-agent"

    def bring_to_front(self):
        pass


class ResolverTests(unittest.TestCase):
    def context(self, page):
        context = SimpleNamespace(
            pages=[page], closed=False, set_default_timeout=lambda value: None,
            cookies=lambda: [], add_cookies=lambda value: None,
        )
        context.close = lambda: setattr(context, "closed", True)
        playwright = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=lambda *args, **kwargs: context))
        return context, playwright

    def test_verification_can_receive_the_requested_video_and_closes_the_browser(self):
        with tempfile.TemporaryDirectory() as temporary:
            context, playwright = self.context(_Page())
            events = []
            config = SessionConfig(Path(temporary), remember=False, resolve_timeout=0, verification_timeout=5)
            with patch("desktop.resolver.sync_playwright", return_value=nullcontext(playwright)):
                result = resolve_work(
                    "https://www.douyin.com/video/123", config, events.append,
                    Event(), Event(), Event(), Event(),
                )
            self.assertEqual(result.video_id, "123")
            self.assertTrue(any(event.get("status") == "verification" for event in events))
            self.assertTrue(context.closed)

    def test_continue_requests_a_reload_in_the_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = _Page()
            context, playwright = self.context(page)
            resume = Event()
            resume.set()
            config = SessionConfig(Path(temporary), remember=False)
            with patch("desktop.resolver.sync_playwright", return_value=nullcontext(playwright)):
                result = resolve_work(
                    "https://www.douyin.com/video/123", config, lambda event: None,
                    Event(), resume, Event(), Event(),
                )
            self.assertEqual(result.video_id, "123")
            self.assertEqual(page.reloads, 1)
            self.assertTrue(context.closed)

    def test_cancel_closes_the_browser_while_waiting(self):
        with tempfile.TemporaryDirectory() as temporary:
            cancel = Event()
            context, playwright = self.context(_Page(cancel))
            config = SessionConfig(Path(temporary), remember=False)
            with patch("desktop.resolver.sync_playwright", return_value=nullcontext(playwright)), self.assertRaises(Cancelled):
                resolve_work(
                    "https://www.douyin.com/video/123", config, lambda event: None,
                    cancel, Event(), Event(), Event(),
                )
            self.assertTrue(context.closed)

    def test_missing_browser_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = SessionConfig(Path(temporary), remember=False)
            playwright = SimpleNamespace(chromium=SimpleNamespace(
                launch_persistent_context=lambda *args, **kwargs: (_ for _ in ()).throw(BrowserError("Executable not found"))
            ))
            with patch("desktop.resolver.sync_playwright", return_value=nullcontext(playwright)), self.assertRaisesRegex(RuntimeError, "切换"):
                resolve_work(
                    "https://www.douyin.com/video/123", config, lambda event: None,
                    Event(), Event(), Event(), Event(),
                )

    def test_note_received_via_post_list_matches_id_and_keeps_image_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            page = _Page()
            page.url = "https://www.douyin.com/note/123"
            def post_response(*args, **kwargs):
                page.callback(SimpleNamespace(
                    url="https://www.douyin.com/aweme/v1/web/aweme/post/?cursor=0", status=200,
                    json=lambda: {"aweme_list": [
                        {"aweme_id": "999", "images": [{"url_list": ["https://example.com/wrong.jpg"]}]},
                        {"aweme_id": "123", "desc": "图文正文", "aweme_type": 68, "images": [
                            {"uri": "one", "url_list": ["https://example.com/one.webp"]},
                            {"uri": "two", "url_list": []},
                        ]},
                    ]},
                ))
            page.goto = post_response
            context, playwright = self.context(page)
            with patch("desktop.resolver.sync_playwright", return_value=nullcontext(playwright)):
                result = resolve_work("https://v.douyin.com/short/", SessionConfig(Path(temporary)),
                                      lambda event: None, Event(), Event(), Event(), Event())
            self.assertEqual(result.work_id, "123")
            self.assertEqual(len(result.images), 2)
            self.assertEqual(result.images[0].key, "one")
            self.assertEqual(result.images[1].urls, [])
            self.assertTrue(context.closed)
