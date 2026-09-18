#!/usr/bin/env python3
"""scripts/extract_slides.py 的单元测试。

用临时构造的最小 .pptx 验证：放映顺序按 presentation.xml（而非文件名）、
页码/页脚占位符被跳过、备注页被提取、页码范围解析与错误处理。
"""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import extract_slides as m

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

PRESENTATION = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P_NS}" xmlns:r="{R_NS}">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId2"/>
    <p:sldId id="257" r:id="rId1"/>
  </p:sldIdLst>
</p:presentation>
"""

PRESENTATION_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="slide" Target="slides/slide2.xml"/>
</Relationships>
"""


def slide_xml(title: str, body: list[str], with_page_number: bool = True) -> str:
    paragraphs = "".join(f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in body)
    page_number = (
        f'<p:sp><p:nvSpPr><p:nvPr><p:ph type="sldNum"/></p:nvPr></p:nvSpPr>'
        f"<p:txBody><a:p><a:r><a:t>99</a:t></a:r></a:p></p:txBody></p:sp>"
        if with_page_number
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="{A_NS}" xmlns:p="{P_NS}" xmlns:r="{R_NS}">
  <p:cSld><p:spTree>
    {page_number}
    <p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:nvPr/></p:nvSpPr><p:txBody>{paragraphs}</p:txBody></p:sp>
    <p:grpSp><p:sp><p:nvSpPr><p:nvPr/></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>组合形状里的字</a:t></a:r></a:p></p:txBody></p:sp></p:grpSp>
  </p:spTree></p:cSld>
</p:sld>
"""


def notes_xml(text: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:notes xmlns:a="{A_NS}" xmlns:p="{P_NS}">
  <p:cSld><p:spTree>
    <p:sp><p:nvSpPr><p:nvPr><p:ph type="sldNum"/></p:nvPr></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>99</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>
  </p:spTree></p:cSld>
</p:notes>
"""

SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="notesSlide" Target="../notesSlides/notesSlide1.xml"/>
</Relationships>
"""


def build_pptx(path: Path, with_notes: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/_rels/presentation.xml.rels", PRESENTATION_RELS)
        archive.writestr("ppt/slides/slide1.xml", slide_xml("A-文件名在前", ["正文一"]))
        archive.writestr("ppt/slides/slide2.xml", slide_xml("B-文件名在后", ["正文二", "第二行"]))
        if with_notes:
            archive.writestr("ppt/slides/_rels/slide1.xml.rels", SLIDE_RELS)
            archive.writestr("ppt/notesSlides/notesSlide1.xml", notes_xml("讲传导顺序"))
    return path


class ReadSlidesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pptx = build_pptx(self.tmp / "课件.pptx")

    def tearDown(self):
        self._tmp.cleanup()

    def test_order_follows_sld_id_list_not_file_name(self):
        slides = m.read_slides(self.pptx)
        self.assertEqual([s.title for s in slides], ["B-文件名在后", "A-文件名在前"])

    def test_skips_page_number_placeholder(self):
        slide = m.read_slides(self.pptx)[1]
        self.assertNotIn("99", slide.lines)
        self.assertIn("正文一", slide.lines)

    def test_reads_grouped_shapes(self):
        self.assertIn("组合形状里的字", m.read_slides(self.pptx)[0].lines)

    def test_reads_notes_without_page_number(self):
        slides = m.read_slides(self.pptx)
        self.assertEqual(slides[1].notes, ["讲传导顺序"])
        self.assertEqual(slides[0].notes, [])

    def test_rejects_non_pptx(self):
        with self.assertRaises(m.PptxError):
            m.read_slides(self.tmp / "课件.pdf")

    def test_rejects_missing_file(self):
        with self.assertRaises(m.PptxError):
            m.read_slides(self.tmp / "不存在.pptx")

    def test_rejects_broken_zip(self):
        broken = self.tmp / "坏.pptx"
        broken.write_text("not a zip", encoding="utf-8")
        with self.assertRaises(m.PptxError):
            m.read_slides(broken)


class SpecTest(unittest.TestCase):
    def test_ranges_and_single_pages(self):
        self.assertEqual(m.parse_slide_spec("1,3-5", 6), {1, 3, 4, 5})

    def test_empty_spec_means_all(self):
        self.assertEqual(m.parse_slide_spec(None, 3), {1, 2, 3})

    def test_out_of_range_filtered(self):
        self.assertEqual(m.parse_slide_spec("2-9", 3), {2, 3})

    def test_reversed_range_is_an_error(self):
        with self.assertRaises(m.PptxError):
            m.parse_slide_spec("5-1", 6)

    def test_garbage_is_an_error(self):
        with self.assertRaises(m.PptxError):
            m.parse_slide_spec("abc", 6)


class OutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pptx = build_pptx(self.tmp / "课件.pptx")

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_mode_is_compact(self):
        slides = m.read_slides(self.pptx)
        self.assertEqual(m.render_list(slides).splitlines()[0], "1\tB-文件名在后")

    def test_render_includes_slide_header_and_notes(self):
        slides = m.read_slides(self.pptx)
        text = m.render(slides, {2}, with_notes=True)
        self.assertIn("[幻灯片 2] A-文件名在前", text)
        self.assertNotIn("[幻灯片 1]", text)

    def test_main_writes_file(self):
        out = self.tmp / "out.txt"
        code = m.main([str(self.pptx), "--list", "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertIn("1\t", out.read_text(encoding="utf-8"))

    def test_main_returns_error_for_bad_input(self):
        self.assertEqual(m.main([str(self.tmp / "无.pdf")]), 1)


if __name__ == "__main__":
    unittest.main()
