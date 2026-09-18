# 课程 Log

> 简短变更记录：材料导入、结构变化、重要笔记变更。不保存每次问答，不复制课程摘要。
> 每门课使用自己的 log，不带入其他课程的历史记录。
> 用法：`grep "^## \[" log.md | head -20`

---

## [2026-09-15] setup | 初始化为跨学科课程学习模板

- 目录结构改为 `index.md` / `教材导航.md` / `raw/` / `lessons/` / `wiki/` / `scripts/` / `AGENTS.md` / `CLAUDE.md` / `log.md`
- `raw/` 下分 `PDF/`、`md/`、`目录/`、`PPT/`、`recordings/`；原件区只读
- 移除旧的 `wiki/{entities,concepts,sources,synthesis,answers}` 子目录分类与 `raw/CLAUDE.md`、`wiki/CLAUDE.md`，规则合并到 `AGENTS.md`
- 移除空的 `assets/`、`raw/assets/`（需要时再按实际用途创建）
- 新增 `scripts/import_srt.py` 及其依赖与测试

---

## [2026-09-15] setup | 增加知识点主干与三个 skill

- 新增 `知识点.md`（K 编号唯一来源）、`PPT导航/`（每份课件一个「幻灯片 → K 编号」导航）
- `教材导航.md` 章节入口增加「知识点」列，只写 K 编号范围
- 新增 skill：`.claude/skills/textbook-knowledge-map`、`ppt-knowledge-map`、`lesson-align`
- 新增 `.pi/settings.json`，把 `.claude/skills` 同时接给 pi，规则只保留一份
- 新增脚本：`scripts/extract_slides.py`（.pptx 逐页文字与备注，标准库实现）、`scripts/find_terms.py`（按术语找候选时间段）
- `scripts/import_srt.py` 生成的转写页增加 `^sNNNN` 区块引用，供课堂页对齐表链接到具体字幕段
- 新增测试 `test_extract_slides.py`、`test_find_terms.py`；`unittest discover` 共 47 项通过


---

## [2026-09-15] setup | 补齐流程文档

- `AGENTS.md` 新增第 2 节「工作流」：按材料类型的处理链、一次课时间线、全库统一的状态词表、复制模板开新课程的步骤、参考文档定位
- 结构图补全 `scripts/`、`.claude/skills/`、`.pi/settings.json`、`医学课程学习框架说明.md`
- 新增 6.5 节：`知识点.md` 与 `PPT导航/` 的格式只在对应 SKILL.md 维护，AGENTS.md 不重复
- `index.md` 使用约定增加规范入口与状态词统一说明

---

## [2026-09-15] setup | paper-search-advisor skill 补 frontmatter

- 目录 `paper_search_advisor/` 改名为 `paper-search-advisor/`，与 name 一致
- `SKILL.md` 补 `name` / `description`，之前没有 frontmatter，两个工具都不会加载
- 新增「文件构成」表，指明 system-prompt.md、keywords-generator.md、databases-config.json、templates/、examples/ 各自何时读取
- 调用示例由 `@search-advisor` 更正为 `@paper-search-advisor`

---

<!-- 后续条目追加于此 -->
