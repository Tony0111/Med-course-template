#!/usr/bin/env python3
"""scripts/import_srt.py 的单元测试。

运行：
    python -B -X utf8 -m unittest discover -s scripts -p "test_*.py"

覆盖面：时间格式、编号/时间轴检查、正文生成、已有阅读页的保护与 --force。
不覆盖：音频内容、音文对齐、教材或 PPT 对齐（这些必须人工核对）。
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import import_srt as m

SRT_OK = """1
00:00:00,000 --> 00:00:02,500
第一句讲解。

2
00:00:02,500 --> 00:00:05,000
第二句讲解，带 A：说话人标签。
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class FormatTsTest(unittest.TestCase):
    def test_formats_hours_minutes_seconds_millis(self):
        self.assertEqual(m.format_ts(timedelta(0)), "00:00:00.000")
        self.assertEqual(m.format_ts(timedelta(seconds=61.5)), "00:01:01.500")
        self.assertEqual(m.format_ts(timedelta(hours=2, minutes=3, seconds=4)), "02:03:04.000")

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            m.format_ts(timedelta(seconds=-1))


class ValidateTest(unittest.TestCase):
    def parse(self, text: str) -> list:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "a.srt", text)
            return m.load_subtitles(path)

    def test_accepts_clean_subtitles(self):
        self.assertEqual(m.validate(self.parse(SRT_OK)), [])

    def test_detects_numbering_gap(self):
        broken = SRT_OK.replace("\n2\n", "\n7\n")
        problems = m.validate(self.parse(broken))
        self.assertTrue(any("编号不连续" in p for p in problems), problems)

    def test_detects_reversed_time_range(self):
        broken = SRT_OK.replace("00:00:02,500 --> 00:00:05,000", "00:00:05,000 --> 00:00:05,000")
        problems = m.validate(self.parse(broken))
        self.assertTrue(any("结束时间不晚于开始时间" in p for p in problems), problems)

    def test_detects_overlap(self):
        broken = SRT_OK.replace("00:00:02,500 --> 00:00:05,000", "00:00:01,000 --> 00:00:05,000")
        problems = m.validate(self.parse(broken))
        self.assertTrue(any("时间重叠" in p for p in problems), problems)

    def test_detects_empty_text(self):
        broken = SRT_OK.replace("第一句讲解。", "   ")
        problems = m.validate(self.parse(broken))
        self.assertTrue(any("没有文字内容" in p for p in problems), problems)

    def test_empty_file_is_a_problem(self):
        self.assertEqual(m.validate([]), ["字幕文件没有解析到任何条目"])


class RenderTest(unittest.TestCase):
    def test_body_is_deterministic_and_keeps_source_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "a.srt", SRT_OK)
            subs = m.load_subtitles(path)
            args = ("L01", subs, "raw/recordings/L01/原始字幕.srt", "deadbeef", "raw/recordings/L01/a.m4a")
            first = m.render_body(*args)
            second = m.render_body(*args)
            self.assertEqual(first, second)
            self.assertIn("00:00:00.000 → 00:00:02.500", first)
            self.assertIn("[0001]", first)
            self.assertIn("A：说话人标签", first)
            self.assertIn("deadbeef", first)


class FrontmatterTest(unittest.TestCase):
    def test_roundtrip(self):
        meta, body = m.split_frontmatter("---\ntype: transcript\nlesson: L01\n---\n\n正文\n")
        self.assertEqual(meta["lesson"], "L01")
        self.assertEqual(body.strip(), "正文")


class MainTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.srt = write(self.tmp / "raw" / "recordings" / "L01" / "原始字幕.srt", SRT_OK)
        self.lessons = self.tmp / "lessons"
        self.out = self.lessons / "L01-转写.md"

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, *extra: str) -> int:
        return m.main(
            [
                "--lesson",
                "L01",
                "--srt",
                str(self.srt),
                "--lessons-dir",
                str(self.lessons),
                *extra,
            ]
        )

    def test_creates_reading_copy(self):
        self.assertEqual(self.run_main(), 0)
        text = self.out.read_text(encoding="utf-8")
        self.assertIn("type: transcript", text)
        self.assertIn("segments: 2", text)
        self.assertIn("duration: 00:00:05.000", text)
        self.assertIn(f"srt-sha256: {m.sha256_bytes(self.srt.read_bytes())}", text)

    def test_rerun_with_same_input_does_not_rewrite(self):
        self.run_main()
        before = self.out.read_text(encoding="utf-8")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.out.read_text(encoding="utf-8"), before)

    def test_refuses_to_overwrite_changed_content(self):
        self.run_main()
        before = self.out.read_text(encoding="utf-8")
        write(self.srt, SRT_OK.replace("第二句讲解", "改写后的第二句讲解"))
        self.assertEqual(self.run_main(), 2)
        self.assertEqual(self.out.read_text(encoding="utf-8"), before)

    def test_force_overwrites(self):
        self.run_main()
        write(self.srt, SRT_OK.replace("第二句讲解", "改写后的第二句讲解"))
        self.assertEqual(self.run_main("--force"), 0)
        self.assertIn("改写后的第二句讲解", self.out.read_text(encoding="utf-8"))

    def test_invalid_subtitles_fail_before_writing(self):
        write(self.srt, "1\n00:00:05,000 --> 00:00:01,000\n倒序时间\n")
        self.assertEqual(self.run_main(), 1)
        self.assertFalse(self.out.exists())

    def test_missing_srt_fails(self):
        missing = self.tmp / "不存在.srt"
        self.assertEqual(
            m.main(["--lesson", "L01", "--srt", str(missing), "--lessons-dir", str(self.lessons)]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
