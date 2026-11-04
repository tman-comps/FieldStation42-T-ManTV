"""
Tests for LiquidSchedule._break_entries, which collects the commercials and bumps
placed in a block's breaks so their play counts get saved with the show's.

Running
-------
    python3 -m unittest test.test_break_play_counts -v
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

from fs42.catalog_entry import CatalogEntry  # noqa: E402
from fs42.liquid_blocks import ReelBlock  # noqa: E402
from fs42.liquid_schedule import LiquidSchedule  # noqa: E402


def _entry(name, tag="commercial"):
    return CatalogEntry(f"/catalog/{name}.mp4", 30, tag)


class TestBreakEntries(unittest.TestCase):
    def test_collects_commercials_and_bumps_from_every_reel(self):
        pre, ad1, ad2, ad3, post = (_entry(n) for n in ("pre", "ad1", "ad2", "ad3", "post"))
        block = SimpleNamespace(reel_blocks=[ReelBlock(pre, [ad1, ad2], None), ReelBlock(None, [ad3], post)])
        self.assertEqual(LiquidSchedule._break_entries(block), [pre, ad1, ad2, ad3, post])

    def test_skips_generated_autobumps(self):
        ad = _entry("ad")
        autobump = SimpleNamespace(path="autobump", duration=5)
        block = SimpleNamespace(reel_blocks=[ReelBlock(autobump, [ad], autobump)])
        self.assertEqual(LiquidSchedule._break_entries(block), [ad])

    def test_blocks_without_breaks(self):
        self.assertEqual(LiquidSchedule._break_entries(SimpleNamespace(reel_blocks=None)), [])
        self.assertEqual(LiquidSchedule._break_entries(SimpleNamespace()), [])


if __name__ == "__main__":
    unittest.main()
