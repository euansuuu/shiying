from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktop.appearance import theme_colors
from desktop.storage import Preferences


def contrast(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class AppearanceTests(unittest.TestCase):
    def test_text_and_controls_have_readable_contrast_in_both_modes(self):
        for mode in ("light", "dark"):
            colors = theme_colors(mode)
            for foreground, background in [
                ("text", "bg"), ("text", "panel"), ("muted", "panel"),
                ("muted", "bg"), ("accent", "tint"), ("warn", "panel"),
                ("success", "panel"), ("onAccent", "buttonStart"), ("onAccent", "buttonEnd"),
            ]:
                with self.subTest(mode=mode, foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5)

    def test_theme_preferences_round_trip_without_changing_download_preferences(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            preferences = Preferences(directory)
            self.assertEqual(preferences.theme, "system")
            preferences.output_dir = str(directory / "中文视频")
            preferences.channel = "chrome"
            preferences.remember = False
            for mode in ("light", "dark", "system"):
                preferences.theme = mode
                preferences.save()
                restored = Preferences(directory)
                self.assertEqual(restored.theme, mode)
                self.assertEqual(restored.output_dir, preferences.output_dir)
                self.assertEqual(restored.channel, "chrome")
                self.assertFalse(restored.remember)

    def test_unknown_saved_theme_falls_back_to_system(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            preferences = Preferences(directory)
            preferences.settings.setValue("theme", "unknown-future-value")
            preferences.settings.sync()
            self.assertEqual(Preferences(directory).theme, "system")
