#!/usr/bin/env python3
"""在课堂转写页里按知识点术语找候选位置：字幕段号 + 起止时间 + 可引用链接。

只读 `lessons/Lxx-转写.md`，不修改它，也不写课堂页；输出候选区间供人工/模型判断。
这些结果只是「候选对应」：命中关键词不等于教师真的讲了该知识点，仍需回听抽查。

    python -B -X utf8 scripts/find_terms.py --lesson L01 --terms "房室结,房室束,传导系统"
    python -B -X utf8 scripts/find_terms.py --transcript lessons/L01-转写.md --term "前负荷" --merge-gap 60

匹配默认忽略字间空格（自动识别字幕常见噪声）；`--exact` 关闭该行为。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BLOCK_RE = re.compile(
    r"^\[(\d{4})\]\s+"
    r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*→\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    r"(?:\s+\^(s\d{4}))?\s*$"
)


class TranscriptError(Exception):
    """转写页无法读取或不像转写页。"""


@dataclass
class Block:
    index: int
    start: str
    end: str
    block_id: str | None
    text: str


@dataclass
class Hit:
    block: Block
    snippet: str


def parse_time(stamp: str) -> float:
    hours, minutes, rest = stamp.split(":")
    seconds, millis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_transcript(path: Path) -> list[Block]:
    if not path.is_file():
        raise TranscriptError(f"找不到转写页：{path}")
    lines = path.read_text(encoding="utf-8").splitlines()

    blocks: list[Block] = []
    current: dict[str, object] | None = None
    for line in lines:
        match = BLOCK_RE.match(line.strip())
        if match:
            if current is not None:
                blocks.append(_finish(current))
            current = {
                "index": int(match.group(1)),
                "start": match.group(2),
                "end": match.group(3),
                "block_id": match.group(4),
                "text": [],
            }
            continue
        if current is not None and line.strip():
            current["text"].append(line.strip())
    if current is not None:
        blocks.append(_finish(current))

    if not blocks:
        raise TranscriptError(
            f"没有解析到任何字幕段：{path}\n"
            "        请确认它是 scripts/import_srt.py 生成的转写页，或先用该脚本重新生成。"
        )
    return blocks


def _finish(current: dict[str, object]) -> Block:
    return Block(
        index=current["index"],  # type: ignore[arg-type]
        start=current["start"],  # type: ignore[arg-type]
        end=current["end"],  # type: ignore[arg-type]
        block_id=current["block_id"],  # type: ignore[arg-type]
        text=" ".join(current["text"]),  # type: ignore[arg-type]
    )


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """去掉所有空白，并保留每个字符在原串中的位置。"""
    chars: list[str] = []
    positions: list[int] = []
    for position, char in enumerate(text):
        if not char.isspace():
            chars.append(char)
            positions.append(position)
    return "".join(chars), positions


def find_hits(blocks: list[Block], term: str, exact: bool = False) -> list[Hit]:
    needle = term if exact else normalize_with_map(term)[0]
    if not needle:
        return []

    hits: list[Hit] = []
    for block in blocks:
        if exact:
            position = block.text.find(needle)
            if position < 0:
                continue
            start, end = position, position + len(needle)
        else:
            normalized, positions = normalize_with_map(block.text)
            position = normalized.find(needle)
            if position < 0:
                continue
            start = positions[position]
            end = positions[min(position + len(needle) - 1, len(positions) - 1)] + 1
        window = 24
        snippet = " ".join(block.text[max(0, start - window) : end + window].split())
        if start - window > 0:
            snippet = "…" + snippet
        if end + window < len(block.text):
            snippet = snippet + "…"
        hits.append(Hit(block=block, snippet=snippet))
    return hits


def merge_ranges(hits: list[Hit], gap_seconds: float) -> list[tuple[float, float, int]]:
    """把时间接近的命中合并为区间，返回 (起, 止, 段数)。"""
    ranges: list[tuple[float, float, int]] = []
    for hit in sorted(hits, key=lambda item: parse_time(item.block.start)):
        start = parse_time(hit.block.start)
        end = parse_time(hit.block.end)
        if ranges and start - ranges[-1][1] <= gap_seconds:
            last_start, last_end, count = ranges[-1]
            ranges[-1] = (last_start, max(last_end, end), count + 1)
        else:
            ranges.append((start, end, 1))
    return ranges


def render_term(
    term: str,
    hits: list[Hit],
    gap_seconds: float,
    max_hits: int,
    link_name: str,
) -> str:
    lines = [f"术语：{term}"]
    if not hits:
        lines.append("  命中 0 段：换用别名、教材原词或更短的词再试；也可能是转写识别有误。")
        return "\n".join(lines)

    lines.append(f"  命中 {len(hits)} 段")
    ranges = merge_ranges(hits, gap_seconds)
    merged = "、".join(
        f"{_stamp(start)} → {_stamp(end)}（{count} 段）" for start, end, count in ranges
    )
    lines.append(f"  候选区间（间隔 ≤{gap_seconds:g}s 合并）：{merged}")
    lines.append("  匹配明细：")
    for hit in hits[:max_hits] if max_hits else hits:
        block = hit.block
        link = f" [[{link_name}#^{block.block_id}]]" if block.block_id else ""
        lines.append(f"    - s{block.index:04d} {block.start} → {block.end}{link}")
        lines.append(f"        {hit.snippet}")
    if max_hits and len(hits) > max_hits:
        lines.append(f"    （其余 {len(hits) - max_hits} 段省略）")
    return "\n".join(lines)


def _stamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在转写页里按术语找候选时间段（只读，不修改转写页）",
    )
    parser.add_argument("--lesson", help="材料编号，如 L01（与 --transcript 二选一）")
    parser.add_argument("--lessons-dir", default="lessons", help="课堂页目录，默认 lessons/")
    parser.add_argument("--transcript", help="转写页路径；默认 lessons/<lesson>-转写.md")
    parser.add_argument("--term", action="append", default=[], help="术语，可重复")
    parser.add_argument("--terms", help="逗号分隔的多个术语")
    parser.add_argument("--merge-gap", type=float, default=120.0, help="合并区间的时间间隔秒数，默认 120")
    parser.add_argument("--max-hits", type=int, default=8, help="每个术语最多列出多少段，0 表示不限，默认 8")
    parser.add_argument("--exact", action="store_true", help="不忽略字间空格")
    parser.add_argument("--link", help="引用用的笔记名；默认取转写页文件名")
    parser.add_argument("--out", help="写入文件而不是标准输出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    terms = list(args.term)
    if args.terms:
        terms.extend(part.strip() for part in args.terms.split(",") if part.strip())
    if not terms:
        print("[错误] 至少给一个术语：--term 或 --terms", file=sys.stderr)
        return 1

    if args.transcript:
        transcript = Path(args.transcript)
    elif args.lesson:
        transcript = Path(args.lessons_dir) / f"{args.lesson}-转写.md"
    else:
        print("[错误] 需要 --lesson 或 --transcript 之一", file=sys.stderr)
        return 1

    try:
        blocks = parse_transcript(transcript)
    except TranscriptError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    link_name = args.link or transcript.stem
    chunks = [
        render_term(term, find_hits(blocks, term, args.exact), args.merge_gap, args.max_hits, link_name)
        for term in terms
    ]
    text = "\n\n".join(chunks) + "\n"

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"[完成] 已写入 {args.out}（{len(blocks)} 段，{len(terms)} 个术语）")
    else:
        sys.stdout.write(text)
    print(
        "[提醒] 以上只是候选位置：命中关键词不等于教师讲了该知识点，"
        "需回听抽查后才能标为「已核对」；段落链接不等于播放器会自动跳到相同秒数。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
