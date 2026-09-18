# scripts/ — 辅助工具

只保留确实用到、收益可验证的自动化。脚本不决定哪些内容是知识结论或重点，也不替人做核对。
三个脚本对应三个 skill 的机械部分：`.claude/skills/{textbook-knowledge-map,ppt-knowledge-map,lesson-align}`。

```powershell
python -B -X utf8 -m unittest discover -s scripts -p "test_*.py"
```

## import_srt.py

把课堂录音的 SRT 字幕转换为可搜索的阅读副本 `lessons/Lxx-转写.md`，便于 Obsidian 搜索，
并让课堂页对齐表链接到具体字幕段（每段末尾的 `^sNNNN`）。

```powershell
python -B -X utf8 scripts/import_srt.py --lesson L01 --srt "raw/recordings/L01/原始字幕.srt" --audio "raw/recordings/L01/原始音频.m4a"
```

- 依赖：Python 3.10+ 与 `srt==3.5.3`（见 `requirements.txt`）。
- 已有的阅读页内容不同时会拒绝覆盖（退出码 2）；确需重建时先保存必要旧版本，再用 `--force`，
  重建后复核原有段落引用。

## extract_slides.py

只读 `.pptx` 原件，按放映顺序提取每页文字与备注，供建立 `PPT导航/<课件名>.md`。
只用标准库（zipfile + ElementTree），不依赖 python-pptx。

```powershell
python -B -X utf8 scripts/extract_slides.py "raw/PPT/L02-心脏.pptx" --list
python -B -X utf8 scripts/extract_slides.py "raw/PPT/L02-心脏.pptx" --slides 12-18 --out out.txt
```

- `--list` 只给页码与标题，适合先看整体；`--slides` 分段读，避免整份课件进上下文。
- 跳过页码/页脚占位符，包含备注页文字；不能读取 `.pdf` 版课件（直接阅读原件）。

## find_terms.py

在转写页里按术语找候选位置，输出字幕段号、起止时间、合并后的候选区间与可引用链接。
只读转写页，不修改它，也不写课堂页。

```powershell
python -B -X utf8 scripts/find_terms.py --lesson L01 --terms "房室结,房室束,传导系统" --merge-gap 120
```

- 默认忽略字间空格（自动识别字幕常见噪声）；`--exact` 关闭该行为。
- `--merge-gap` 控制区间合并；`--max-hits 0` 列出全部命中。

## 三个脚本共同不做的事

不检查音频总时长、不识别音频内容、不完成音文对齐、不判断讲解内容是否讲了该知识点、
不做教材或 PPT 对齐。输出都是**候选**，新课程必须独立核对（首次导入尤其要确认音频与字幕是否匹配），
不能沿用其他课程的检查结论。转写页与 PPT 导航里的状态，只有人工核对手写后才算 `已核对`。
