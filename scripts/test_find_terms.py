#!/usr/bin/env python3
"""scripts/find_terms.py 的单元测试。

验证：转写页解析、字间空格容错、区间合并、引用链接、退出码，
并与 import_srt.py 生成的页面做一次格式兼容性联测。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import find_terms as f
import import_srt as i

TRANSCRIPT = """---
type: transcript
lesson: L01
---

# L01 课堂转写

[0001] 00:00:00.000 → 00:00:05.000 ^s0001

今天讲房室结的功能。

[0002] 00:00:10.000 → 00:00:15.000 ^s0002

房室 结 有传导延搁，是本次课重点。

[0003] 00:05:00.000 → 00:05:06.000 ^s0003

后面再讲房室 结 与房室束的区别。
"""

SRT = """1
00:00:00,000 --> 00:00:04,000
先说房室结。

2
00:00:04,000 --> 00:00:08,000
再说房室束。
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ParseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = write(Path(self._tmp.name) / "L01-转写.md", TRANSCRIPT)

    def tearDown(self):
        self._tmp.cleanup()

    def test_parses_blocks_and_text(self):
        blocks = f.parse_transcript(self.path)
        self.assertEqual([b.index for b in blocks], [1, 2, 3])
        self.assertEqual(blocks[1].block_id, "s0002")
        self.assertIn("传导延搁", blocks[1].text)

    def test_missing_file_is_an_error(self):
        with self.assertRaises(f.TranscriptError):
            f.parse_transcript(self.path.parent / "无.md")

    def test_non_transcript_is_an_error(self):
        plain = write(self.path.parent / "普通.md", "# 只是笔记\n\n没有字幕段。\n")
        with self.assertRaises(f.TranscriptError):
            f.parse_transcript(plain)


class SearchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = write(Path(self._tmp.name) / "L01-转写.md", TRANSCRIPT)
        self.blocks = f.parse_transcript(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_matches_despite_spaces_between_characters(self):
        hits = f.find_hits(self.blocks, "房室结")
        self.assertEqual([h.block.index for h in hits], [1, 2, 3])

    def test_exact_mode_does_not_tolerate_spaces(self):
        hits = f.find_hits(self.blocks, "房室结", exact=True)
        self.assertEqual([h.block.index for h in hits], [1])

    def test_snippet_contains_matched_text(self):
        hits = f.find_hits(self.blocks, "房室束")
        self.assertIn("房室束", hits[0].snippet)

    def test_absent_term_yields_no_hits(self):
        self.assertEqual(f.find_hits(self.blocks, "不存在的词"), [])

    def test_merges_nearby_hits_and_keeps_distant_ones(self):
        hits = f.find_hits(self.blocks, "房室结")
        ranges = f.merge_ranges(hits, gap_seconds=120)
        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0][2], 2)
        self.assertAlmostEqual(ranges[0][0], 0.0)
        self.assertAlmostEqual(ranges[1][0], 300.0)

    def test_render_includes_block_link(self):
        text = f.render_term("房室结", f.find_hits(self.blocks, "房室结"), 120, 8, "L01-转写")
        self.assertIn("[[L01-转写#^s0001]]", text)
        self.assertIn("候选区间", text)

    def test_render_reports_zero_hits_explicitly(self):
        text = f.render_term("没有的词", [], 120, 8, "L01-转写")
        self.assertIn("命中 0 段", text)


class MainTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.path = write(self.tmp / "lessons" / "L01-转写.md", TRANSCRIPT)

    def tearDown(self):
        self._tmp.cleanup()

    def test_runs_and_writes_output(self):
        out = self.tmp / "候选.txt"
        code = f.main(["--lesson", "L01", "--lessons-dir", str(self.tmp / "lessons"),
                       "--terms", "房室结,房室束", "--out", str(out)])
        self.assertEqual(code, 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("术语：房室结", text)
        self.assertIn("术语：房室束", text)

    def test_requires_terms(self):
        self.assertEqual(f.main(["--transcript", str(self.path)]), 1)

    def test_requires_a_source(self):
        self.assertEqual(f.main(["--term", "房室结"]), 1)

    def test_missing_transcript_returns_error(self):
        self.assertEqual(
            f.main(["--transcript", str(self.tmp / "无.md"), "--term", "房室结"]), 1
        )


class CompatibilityTest(unittest.TestCase):
    """与 import_srt.py 生成的页面联测：脚本产出必须能被 find_terms 解析。"""

    def test_generated_page_is_searchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt_path = write(root / "raw" / "a.srt", SRT)
            code = i.main(["--lesson", "L01", "--srt", str(srt_path),
                           "--lessons-dir", str(root / "lessons")])
            self.assertEqual(code, 0)
            blocks = f.parse_transcript(root / "lessons" / "L01-转写.md")
            self.assertEqual([b.index for b in blocks], [1, 2])
            hits = f.find_hits(blocks, "房室束")
            self.assertEqual([h.block.index for h in hits], [2])
            text = f.render_term("房室束", hits, 120, 8, "L01-转写")
            self.assertIn("[[L01-转写#^s0002]]", text)


if __name__ == "__main__":
    unittest.main()
