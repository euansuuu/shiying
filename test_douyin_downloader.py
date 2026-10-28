import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from yt_dlp.utils import DownloadError

from douyin_downloader import _browser_cookie_option, download_douyin, extract_douyin_url


class ExtractDouyinUrlTests(unittest.TestCase):
    def test_short_url_with_mixed_slug(self) -> None:
        text = "复制打开抖音 https://v.douyin.com/AbC_12-xY/ 观看视频"
        self.assertEqual(
            extract_douyin_url(text),
            "https://v.douyin.com/AbC_12-xY/",
        )

    def test_full_video_url(self) -> None:
        url = "https://www.douyin.com/video/1234567890123456789?from=web"
        self.assertEqual(extract_douyin_url(url), url)

    def test_invalid_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "未找到"):
            extract_douyin_url("这里没有链接")

    def test_browser_name_is_normalized(self) -> None:
        self.assertEqual(_browser_cookie_option("Edge"), ("edge", None, None, None))

    def test_browser_profile_is_forwarded(self) -> None:
        self.assertEqual(
            _browser_cookie_option("chrome", "Profile 1"),
            ("chrome", "Profile 1", None, None),
        )

    def test_unknown_browser_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "不支持"):
            _browser_cookie_option("unknown")

    def test_locked_chrome_cookie_database_has_actionable_hint(self) -> None:
        error = DownloadError("Could not copy Chrome cookie database")
        with TemporaryDirectory() as directory, patch(
            "douyin_downloader.yt_dlp.YoutubeDL", side_effect=error
        ):
            with self.assertRaisesRegex(RuntimeError, "完全退出 Chrome"):
                download_douyin(
                    "https://v.douyin.com/AbC_12-xY/",
                    Path(directory),
                    browser="chrome",
                )

    def test_dpapi_failure_recommends_browser_session(self) -> None:
        error = DownloadError("Failed to decrypt with DPAPI")
        with TemporaryDirectory() as directory, patch(
            "douyin_downloader.yt_dlp.YoutubeDL", side_effect=error
        ):
            with self.assertRaisesRegex(RuntimeError, "--browser-session chrome"):
                download_douyin(
                    "https://v.douyin.com/AbC_12-xY/",
                    Path(directory),
                    browser="chrome",
                )


if __name__ == "__main__":
    unittest.main()
