## Context

当前 `local_folder` 适配器对 PDF 的正文抽取只在 `_extract_pdf` 里调用 PyMuPDF `page.get_text()`（文本层）。对扫描件/图片型 PDF（无文本层）或字体编码损坏的 PDF（缺 `ToUnicode CMap`、自定义 CID 字体），返回空串或乱码字形码。这串乱码原样存为 `InfoItem.content` 发给 LLM，LLM 报"无意义编码字符串"，仅靠文件名推断。

环境核查结论：
- PyMuPDF 1.25.2 已支持 `page.get_pixmap()` 页面渲染，无需新增渲染依赖。
- 默认 LLM `gpt-4o-mini` 支持视觉，但 `LLMClient.chat()` 只发纯文本。
- 系统已能从 PDF 抽出内嵌图片（`extract_figures`），但仅作邮件附件，未参与分析。
- `pytesseract`/`Pillow` 未安装；用户已选定**视觉 LLM 兜底**方案（不引入 Tesseract）。

约束：遵循 CLAUDE.md 规范（不硬编码环境信息、SQLite 优先、北京时间显示、配置化、测试通过、Jenkins 部署）。

## Goals / Non-Goals

**Goals:**
- 对文本层不可用的 PDF，用视觉 LLM 兜底抽出可读正文，使扫描页/图表/表格也能被分析。
- 保持"先抽取、后分析"架构：`content` 始终为可复用纯文本，分析引擎与提示词无感知。
- 可配置、可关闭，视觉不可用时优雅降级，绝不中断同步/分析。
- 记录抽取来源 `extraction_method`，支持历史坏条目重抽。

**Non-Goals:**
- 不引入 Tesseract OCR（用户未选；留作未来可选项，配置位预留但不实现）。
- 不改造分析引擎 `engine.py` 与提示词 `prompts.py` 的流程。
- 不处理独立图片文件（png/jpg）与 docx 仅含图片的场景（未来扩展）。
- 不做"把图片直接发给分析 LLM"的 analyze-directly 模式（见决策 1）。

## Decisions

### 决策 1：抽取-再-分析（extract-then-analyze），而非直接分析图片
视觉 LLM 先把页面图片转成文本，存入 `InfoItem.content`，分析侧沿用现有纯文本流程。
- **理由**：content 可复用（搜索、展示、重分析无需重渲染）、与分析解耦、现有提示词与 `engine.py` 零改动。
- **备选**：把页面图片连同分析提示词一次性发给视觉 LLM（少一次调用、能"看图说话"）。否决：抽取与分析耦合、无可复用文本、重分析须重渲染重付费、难以对历史内容重跑不同提示词。
- **代价**：兜底条目多一次"抽取"调用，再走一次"分析"调用（共两次）。可接受：仅对文本层失败的条目触发，受页数上限约束。

### 决策 2：文本质量评估用轻量启发式（可读字符占比 + 最小长度）
判定文本层不可用的条件：结果为空、或长度 < `min_text_length`（默认 50）、或可读占比 < `readable_ratio`（默认 0.6）。可读字符 = CJK 统一汉字 + 拉丁字母 + 数字 + 常用标点；占比 = 可读数 / 非空白字符数。
- **理由**：零成本、确定性、可单测；乱码字形码（私用区/符号汤）可读占比极低，能稳定识别。
- **备选**：①始终跑视觉兜底（浪费、慢、贵）；②用 LLM 判质量（贵、慢、引入循环依赖）。均否决。
- **风险**：合法的极短/符号密集 PDF 可能误触发兜底。缓解：阈值可配置；视觉结果非空才覆盖，否则保留原值。

### 决策 3：页面渲染用 PyMuPDF `get_pixmap`，逐页调用视觉 LLM
用 `page.get_pixmap(dpi=...)` 渲染为 PNG 字节，base64 编码为 data URI，逐页调用多模态 LLM 提取该页文本，按页序拼接。`dpi` 默认 150（清晰度与 token 成本平衡），`max_ocr_pages` 默认 10，超限截断并记日志。
- **理由**：PyMuPDF 已安装，无需 pdf2image/Pillow；逐页调用避免单请求 token 超限，失败可按页降级。
- **备选**：①`pdf2image`+Pillow（多两个依赖）；②多页拼一张图一次调用（token 易超、失败全丢）。均否决。
- **提示词**：每页调用带页码的简短指令，如"请提取并原样输出这张文档第 N 页的全部正文文本，保留段落结构，仅输出文本，不要解说"。

### 决策 4：`LLMClient` 新增 `chat_with_images`，不动 `chat`
新增 `chat_with_images(system, user_text, images: list[bytes], mime="image/png") -> str`，按 OpenAI 视觉格式构造 user message：`[{"type":"text","text":...}, {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]`。`chat` 纯文本行为不变。
- **理由**：显式方法、职责清晰、对现有调用方零影响；OpenAI 兼容 endpoint 通用。
- **备选**：通用 `chat(messages)` 透传。否决：现有 `chat(system,user)` 签名被多处复用与单测，改动面大。
- **降级**：视觉调用复用现有重试与超时逻辑；任何异常（含 endpoint 不支持视觉返回 4xx）被上层 try/except 捕获 → 优雅降级。

### 决策 5：`InfoItem` 新增 `extraction_method` 列（可空）
新增 `extraction_method: str | None`（`text_layer`/`vision_llm`/`none`）。现有行迁移为 NULL（视为未知/文本层）。
- **理由**：真实列可查询，backfill 与 UI 展示可直接筛选"待重抽"条目。
- **备选**：存入 JSON extra。否决：不可查询、不便筛选。
- **迁移**：SQLite `ALTER TABLE info_items ADD COLUMN extraction_method TEXT`；项目用 `Base.metadata.create_all` 建表，需在启动迁移逻辑里对已存在库补加该列（幂等检查）。

### 决策 6：配置新增 `extraction` 节，支持 `ISAS_EXTRACTION_*` 环境变量覆盖
`config/app.json` 新增：
```json
"extraction": {
  "vision_fallback": true,
  "vision_model": "",
  "max_ocr_pages": 10,
  "min_text_length": 50,
  "readable_ratio": 0.6,
  "render_dpi": 150
}
```
`vision_model` 为空时复用 `llm.model`。`core/config.py` 增对应字段与 env 覆盖。
- **理由**：遵循"配置化、不硬编码"规范；开关默认开但仅在文本层失败时触发，对原生数字 PDF 零影响。

### 决策 7：复用 backfill 与 `reextract_item` 触发重抽
`sync.py` 的 backfill 选择条件扩展：除现有"author/page_count 为空"外，纳入"`extraction_method` 为 `none` 或 `content` 为空"的条目。`reextract_item` 因走 `_extract_full` 自然获得视觉兜底能力。
- **理由**：复用既有重抽管线，不新增 API；用户可手动重抽坏条目，也可在同步时自动回补。

## Risks / Trade-offs

- **[API 成本随页数线性增长]** → `max_ocr_pages` 上限 + 仅文本层失败才触发 + DPI 可调；默认 10 页/150 DPI。
- **[配置的 LLM endpoint 不支持视觉]** → 优雅降级：捕获 4xx/格式异常，记警告，`extraction_method=none`，保留原 content；文档注明视觉兜底需多模态模型，可配独立 `vision_model` 指向支持视觉的模型。
- **[视觉抽取慢、阻塞同步 worker]** → 受 `max_ocr_pages` 约束；逐页调用，单页失败不阻断其余页；同步在后台 worker 运行，不阻塞 API。
- **[质量启发式误判]** → 阈值可配置；视觉结果为空时不覆盖原 content。
- **[SQLite 加列迁移]** → 幂等 `ALTER TABLE` + 列存在检查；现有行 NULL 不影响逻辑（NULL 视为未知，backfill 会纳入重抽）。
- **[多页拼接顺序/重复]** → 严格按页序拼接，提示词要求"仅输出文本"，降低重复与解说噪声。

## Migration Plan

1. **代码**：新增 `extraction_method` 列与启动迁移；扩展 `LLMClient`、`local_folder`、`sync`、`config`。
2. **部署**：无新系统依赖，`requirements.txt` 不变；`Jenkinsfile` 无结构变化，`pip install -r requirements.txt` 照旧。
3. **配置**：`extraction` 节默认启用兜底；对原生数字 PDF 无行为变化（文本层成功即不触发）。
4. **回填**：部署后触发一次同步（backfill 自动纳入 `extraction_method=none`/空 content 条目）或在 UI 手动重抽；重抽后 `analyzed` 置回 False，下次分析任务自动重跑。
5. **回滚**：将 `extraction.vision_fallback` 置 false 即恢复纯文本层行为；代码回滚需同步移除新列（可保留，nullable 不影响旧代码）。

## Open Questions

- 默认 `max_ocr_pages`（10）与 `render_dpi`（150）是否需要按实际经济报告篇幅/清晰度调整？（实现后用真实样本校准。）
- 视觉抽取是否需要把"页面图表"也单独描述输出（而非仅正文文本）？当前 Non-Goal，仅抽正文；图表仍由 `extract_figures` 单独抽取并附邮件。
