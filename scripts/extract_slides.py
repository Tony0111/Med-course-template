#!/usr/bin/env python3
"""从 .pptx 提取每页文字与备注，供 AI 建立 PPT 导航（幻灯片 → 知识点）。

只读原件，不修改、不导出新文件；输出为纯文本，便于按需只读若干页。

    python -B -X utf8 scripts/extract_slides.py "raw/PPT/L02-心脏.pptx" --list
    python -B -X utf8 scripts/extract_slides.py "raw/PPT/L02-心脏.pptx" --slides 12-18

只用标准库（zipfile + ElementTree），不依赖 python-pptx。
.pdf 版课件不需要本脚本，直接阅读原文件。
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import xml.etree.ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"a": A, "p": P, "r": R}

# 页码、页脚、日期等占位符不是课件内容
SKIP_PLACEHOLDERS = {"sldNum", "sldImg", "dt", "ftr"}
SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


class PptxError(Exception):
    """课件无法读取或不是有效的 .pptx。"""


@dataclass
class Slide:
    number: int
    title: str | None
    lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.title:
            return self.title
        return self.lines[0] if self.lines else "（无文字）"


def _read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        data = archive.read(name)
    except KeyError as exc:
        raise PptxError(f"压缩包内缺少 {name}（可能不是 .pptx 文件）") from exc
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise PptxError(f"无法解析 {name}：{exc}") from exc


def _rels(archive: zipfile.ZipFile, part: str) -> dict[str, str]:
    """读取 part 的关系表，返回 {rId: 规范化后的内部路径}。"""
    base = posixpath.dirname(part)
    rels_name = posixpath.join(base, "_rels", posixpath.basename(part) + ".rels")
    if rels_name not in archive.namelist():
        return {}
    rels: dict[str, str] = {}
    for rel in _read_xml(archive, rels_name):
        target = rel.get("Target")
        if not target or rel.get("TargetMode") == "External":
            continue
        rels[rel.get("Id", "")] = posixpath.normpath(posixpath.join(base, target))
    return rels


def slide_parts(archive: zipfile.ZipFile) -> list[str]:
    """按放映顺序返回幻灯片文件路径（依 presentation.xml 的 sldIdLst + 关系表）。"""
    order: list[str] = []
    try:
        rels = _rels(archive, "ppt/presentation.xml")
        root = _read_xml(archive, "ppt/presentation.xml")
    except PptxError:
        rels, root = {}, None
    if root is not None:
        lst = root.find("p:sldIdLst", NS)
        if lst is not None:
            for sld in lst:
                target = rels.get(sld.get(f"{{{R}}}id", ""))
                if target and target not in order:
                    order.append(target)
    if not order:  # 关系表缺失时按文件名数字排序兜底
        order = sorted(
            (name for name in archive.namelist() if SLIDE_RE.match(name)),
            key=lambda name: int(SLIDE_RE.match(name).group(1)),  # type: ignore[union-attr]
        )
    return order


def _paragraphs(shape: ET.Element) -> list[str]:
    lines: list[str] = []
    for para in shape.findall(".//a:p", NS):
        text = "".join(run.text or "" for run in para.findall(".//a:t", NS)).strip()
        if text:
            lines.append(text)
    return lines


def _walk_shapes(container: ET.Element) -> Iterator[list[str]]:
    """自上而下遍历形状，跳过页码/页脚类占位符，避免重复取文字。"""
    for child in container:
        tag = child.tag
        if tag == f"{{{P}}}grpSp":
            yield from _walk_shapes(child)
            continue
        if tag not in (f"{{{P}}}sp", f"{{{P}}}graphicFrame", f"{{{P}}}pic"):
            continue
        placeholder = child.find(".//p:ph", NS)
        if placeholder is not None and (placeholder.get("type") or "body") in SKIP_PLACEHOLDERS:
            continue
        lines = _paragraphs(child)
        if lines:
            yield lines


def _sp_tree(root: ET.Element) -> ET.Element | None:
    return root.find(".//p:cSld/p:spTree", NS)


def _slide_title(root: ET.Element) -> list[str]:
    """返回标题占位符的段落（已去重为空时返回空表）。"""
    tree = _sp_tree(root)
    if tree is None:
        return []
    for shape in tree.iter(f"{{{P}}}sp"):
        placeholder = shape.find(".//p:ph", NS)
        if placeholder is not None and placeholder.get("type") in ("title", "ctrTitle"):
            lines = _paragraphs(shape)
            if lines:
                return lines
    return []


def _notes(archive: zipfile.ZipFile, slide_part: str) -> list[str]:
    for target in _rels(archive, slide_part).values():
        if "notesSlide" not in target:
            continue
        tree = _sp_tree(_read_xml(archive, target))
        if tree is None:
            return []
        return [line for block in _walk_shapes(tree) for line in block]
    return []


def read_slides(pptx: Path) -> list[Slide]:
    if not pptx.is_file():
        raise PptxError(f"找不到课件文件：{pptx}")
    if pptx.suffix.lower() != ".pptx":
        raise PptxError(f"只支持 .pptx 原件（{pptx.suffix}）；.pdf 版课件请直接阅读原文件")
    try:
        archive = zipfile.ZipFile(pptx)
    except zipfile.BadZipFile as exc:
        raise PptxError(f"无法打开 {pptx}：{exc}") from exc

    with archive:
        slides: list[Slide] = []
        for index, part in enumerate(slide_parts(archive), start=1):
            root = _read_xml(archive, part)
            tree = _sp_tree(root)
            lines = [line for block in _walk_shapes(tree) for line in block] if tree is not None else []
            title_lines = _slide_title(root)
            # 标题已在页码行展示，正文里不再重复
            lines = [line for line in lines if line not in title_lines]
            slides.append(
                Slide(
                    number=index,
                    title=" / ".join(title_lines) if title_lines else None,
                    lines=lines,
                    notes=_notes(archive, part),
                )
            )
        return slides


def parse_slide_spec(spec: str | None, total: int) -> set[int]:
    if not spec:
        return set(range(1, total + 1))
    wanted: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, _, end_text = chunk.partition("-")
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise PptxError(f"页码范围无法解析：{chunk}") from exc
            if start > end:
                raise PptxError(f"页码范围颠倒：{chunk}")
            wanted.update(range(start, end + 1))
        else:
            try:
                wanted.add(int(chunk))
            except ValueError as exc:
                raise PptxError(f"页码无法解析：{chunk}") from exc
    return {number for number in wanted if 1 <= number <= total}


def render(slides: list[Slide], selected: set[int], with_notes: bool) -> str:
    chunks: list[str] = []
    for slide in slides:
        if slide.number not in selected:
            continue
        head = f"[幻灯片 {slide.number}]"
        if slide.title:
            head += f" {slide.title}"
        body = "\n".join(slide.lines) if slide.lines else "（无文字，可能只有图）"
        block = f"{head}\n{body}"
        if with_notes and slide.notes:
            block += "\n> 备注：" + " / ".join(slide.notes)
        chunks.append(block)
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def render_list(slides: list[Slide]) -> str:
    return "\n".join(f"{slide.number}\t{slide.label}" for slide in slides) + ("\n" if slides else "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="提取 .pptx 每页文字与备注（只读，不改原件）")
    parser.add_argument("pptx", help="课件原件路径，如 raw/PPT/L02-心脏.pptx")
    parser.add_argument("--list", action="store_true", help="只输出页码与标题，便于先做整体映射")
    parser.add_argument("--slides", help="只取指定页，如 3-5,8（1 起算）")
    parser.add_argument("--no-notes", action="store_true", help="不输出备注页文字")
    parser.add_argument("--out", help="写入文件而不是标准输出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        slides = read_slides(Path(args.pptx))
        if not slides:
            raise PptxError("课件里没有解析到任何幻灯片")
        selected = parse_slide_spec(args.slides, len(slides))
        if not selected:
            raise PptxError("--slides 选中的页在课件范围内不存在")
        text = render_list(slides) if args.list else render(slides, selected, not args.no_notes)
    except PptxError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"[完成] 已写入 {args.out}：共 {len(slides)} 页，导出 {len(selected)} 页")
    else:
        sys.stdout.write(text)
    print(
        "[提醒] 文字提取不含图片、图表与版式；形态图、流程、表格需回看原文件，"
        "页码与标题差异以原件为准。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
