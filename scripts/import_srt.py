#!/usr/bin/env python3
"""把课堂录音的 SRT 字幕转换为可搜索的阅读副本 lessons/Lxx-转写.md。

用途：让 Obsidian 能搜索字幕文字，并让课堂页或知识笔记链接到具体字幕段落。
本脚本只做重复、可验证的部分：格式检查、连续编号、有效时间范围、区间重叠检查，
并拒绝覆盖内容不同的已有阅读页。

它不做的事：不检查音频总时长、不识别音频内容、不核对音文是否对齐、
不完成教材或 PPT 对齐。新课程必须独立核对，不能沿用其他课程的检查结论。

用法（Windows PowerShell，参数按实际原文件路径替换）：

    python -B -X utf8 scripts/import_srt.py --lesson L01 ^
        --srt "raw/recordings/L01/原始字幕.srt" ^
        --audio "raw/recordings/L01/原始音频.m4a"

退出码：0 成功或内容无变化；1 校验失败；2 拒绝覆盖已有阅读页。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import srt

FRONTMATTER_FENCE = "---"
GENERATOR = "scripts/import_srt.py"


class ValidationFailed(Exception):
    """字幕未通过格式或时间轴检查。"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def format_ts(value: timedelta) -> str:
    """timedelta -> HH:MM:SS.mmm"""
    total_ms = int(round(value.total_seconds() * 1000))
    if total_ms < 0:
        raise ValueError("时间不能为负")
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def load_subtitles(srt_path: Path) -> list[srt.Subtitle]:
    raw = srt_path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:  # 常见于 GBK 字幕
        raise ValidationFailed(f"字幕不是 UTF-8 编码：{srt_path}（{exc}）") from exc
    # 统一换行，避免 CRLF 造成的行尾噪声混入正文
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        return list(srt.parse(text))
    except srt.SRTParseError as exc:
        raise ValidationFailed(f"字幕格式无法解析：{srt_path}（{exc}）") from exc


def validate(subtitles: list[srt.Subtitle]) -> list[str]:
    """返回问题列表；空列表表示通过。"""
    problems: list[str] = []
    if not subtitles:
        return ["字幕文件没有解析到任何条目"]

    previous: srt.Subtitle | None = None
    for position, sub in enumerate(subtitles, start=1):
        if sub.index != position:
            problems.append(f"编号不连续：第 {position} 条的编号是 {sub.index}")
        if sub.end <= sub.start:
            problems.append(
                f"第 {sub.index} 条结束时间不晚于开始时间"
                f"（{format_ts(sub.start)} -> {format_ts(sub.end)}）"
            )
        if not sub.content.strip():
            problems.append(f"第 {sub.index} 条没有文字内容")
        if previous is not None and sub.start < previous.end:
            problems.append(
                f"第 {sub.index} 条与第 {previous.index} 条时间重叠"
                f"（{format_ts(previous.end)} > {format_ts(sub.start)}）"
            )
        previous = sub
    return problems


def render_body(
    lesson: str,
    subtitles: list[srt.Subtitle],
    srt_display: str,
    srt_hash: str,
    audio_display: str | None,
) -> str:
    """生成正文。内容与生成时间无关，便于比较已有页面是否变化。"""
    lines: list[str] = [
        f"# {lesson} 课堂转写",
        "",
        f"> 由 `{GENERATOR}` 从 SRT 生成的可重建阅读副本，请勿手工修改。",
        "> 每段末尾的 `^sNNNN` 是区块引用，可在课堂页对齐表里用 `[[本页名#^s0012]]` 定位字幕段。",
        f"> 源字幕：`{srt_display}`（sha256 `{srt_hash}`）",
    ]
    if audio_display:
        lines.append(f"> 音频：`{audio_display}`（时间范围可直接用于回听定位）")
    lines.append("")

    for sub in subtitles:
        stamp = f"{format_ts(sub.start)} → {format_ts(sub.end)}"
        # ^sNNNN 是 Obsidian 区块引用，供课堂页对齐表链接到具体字幕段
        lines.append(f"[{sub.index:04d}] {stamp} ^s{sub.index:04d}")
        lines.append("")
        lines.append(sub.content.strip())
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_page(
    lesson: str,
    body: str,
    srt_display: str,
    srt_hash: str,
    audio_display: str | None,
    segments: int,
    duration: str,
    today: str,
) -> str:
    frontmatter = [
        FRONTMATTER_FENCE,
        "type: transcript",
        f"lesson: {lesson}",
        f"srt: {srt_display}",
        f"srt-sha256: {srt_hash}",
    ]
    if audio_display:
        frontmatter.append(f"audio: {audio_display}")
    frontmatter += [
        f"segments: {segments}",
        f"duration: {duration}",
        f"content-hash: {sha256_text(body)}",
        f"generated: {today}",
        f"generated-by: {GENERATOR}",
        FRONTMATTER_FENCE,
    ]
    return "\n".join(frontmatter) + "\n\n" + body


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """拆出简单 YAML frontmatter（仅支持 key: value）与正文。"""
    if not text.startswith(FRONTMATTER_FENCE):
        return {}, text
    parts = text.split(FRONTMATTER_FENCE, 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, parts[2].lstrip("\n")


def existing_body_hash(path: Path) -> str | None:
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    recorded = meta.get("content-hash")
    if recorded:
        return recorded
    return sha256_text(body) if body else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把 SRT 字幕转换为 lessons/Lxx-转写.md（可搜索的阅读副本）",
    )
    parser.add_argument("--lesson", required=True, help="库内材料编号，如 L01")
    parser.add_argument("--srt", required=True, help="原始字幕文件路径")
    parser.add_argument("--audio", help="原始音频文件路径（可选，仅登记与核对用）")
    parser.add_argument(
        "--lessons-dir",
        default="lessons",
        help="课堂页目录，默认 lessons/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="已有阅读页内容不同时仍覆盖（覆盖前请先保存需要的旧版本）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    srt_path = Path(args.srt)
    if not srt_path.is_file():
        print(f"[错误] 找不到字幕文件：{srt_path}", file=sys.stderr)
        return 1

    audio_display: str | None = None
    if args.audio:
        audio_display = args.audio
        if not Path(args.audio).is_file():
            print(f"[提醒] 音频文件不在该路径，仅登记路径不校验内容：{args.audio}", file=sys.stderr)

    try:
        subtitles = load_subtitles(srt_path)
    except ValidationFailed as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    problems = validate(subtitles)
    if problems:
        print(f"[错误] 字幕未通过检查，共 {len(problems)} 项：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("  修正 SRT 后再运行；不要把问题字幕当成已核对结果。", file=sys.stderr)
        return 1

    srt_hash = sha256_bytes(srt_path.read_bytes())
    body = render_body(args.lesson, subtitles, args.srt, srt_hash, audio_display)
    out_path = Path(args.lessons_dir) / f"{args.lesson}-转写.md"

    if out_path.exists():
        old_hash = existing_body_hash(out_path)
        if old_hash == sha256_text(body):
            print(f"[跳过] 内容与已有阅读页一致，未改动：{out_path}")
            return 0
        if not args.force:
            print(
                f"[拒绝] 已有阅读页内容与本次生成结果不同：{out_path}\n"
                "        请先核对差异，必要时保存旧版本，再用 --force 重建；"
                "重建后需复核原有段落引用。",
                file=sys.stderr,
            )
            return 2

    page = render_page(
        lesson=args.lesson,
        body=body,
        srt_display=args.srt,
        srt_hash=srt_hash,
        audio_display=audio_display,
        segments=len(subtitles),
        duration=format_ts(subtitles[-1].end),
        today=datetime.now().strftime("%Y-%m-%d"),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8", newline="\n")
    first, last = format_ts(subtitles[0].start), format_ts(subtitles[-1].end)
    print(f"[完成] {out_path}：{len(subtitles)} 条字幕，{first} → {last}")
    print("       本脚本未核对音文对齐，请另行抽查时间轴与抽样内容。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
