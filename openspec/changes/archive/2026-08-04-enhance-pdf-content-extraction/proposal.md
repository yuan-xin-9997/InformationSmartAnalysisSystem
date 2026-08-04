## Why

PDF 正文抽取只依赖文本层（`local_folder.py` 的 `_extract_pdf` 用 PyMuPDF `page.get_text()`）。对**扫描件/图片型 PDF**（无文本层）或**字体编码损坏的 PDF**（缺 `ToUnicode CMap`、自定义 CID 字体），`get_text()` 返回空串或乱码字形码。这串乱码被原样存为 `InfoItem.content` 发给 LLM，LLM 报告"正文内容为一段无意义编码字符串，无法提取具体经济数据"，仅能基于文件名做有限推断。系统其实已能抽出 PDF 内嵌图片（`extract_figures`），却只用作邮件附件、从未参与分析。需要为这类 PDF 增加正文兜底抽取，使扫描页、图表、表格也能被"读"到。

## What Changes

- 在 `local_folder` 的 PDF 抽取流程中新增**文本质量评估**：当 `page.get_text()` 结果为空、过短，或可读字符占比低于阈值时，判定文本层不可用。
- 文本层不可用时启用**视觉 LLM 兜底抽取**：用 PyMuPDF `page.get_pixmap()` 把页面渲染成图片，调用多模态 LLM 提取正文文本，作为 `InfoItem.content` 落库（"先抽取、后分析"架构不变，content 始终为可复用文本）。
- 扩展 `LLMClient` 支持 OpenAI 视觉消息格式（`image_url` + base64 data URI），新增 `chat_with_images` 方法；现有 `chat` 纯文本行为不变。
- 新增可配置项：是否启用视觉兜底、兜底模型（可独立于分析模型）、单文件最大渲染页数、触发兜底的质量阈值、渲染 DPI。
- `InfoItem` 新增 `extraction_method` 字段（`text_layer` / `vision_llm` / `none`）记录正文来源，便于追溯与重抽筛选。
- 复用既有 backfill / `reextract_item` 机制：对历史 `content` 为空或乱码的条目，在同步与手动重抽时自动走视觉兜底重新抽取。
- 视觉 LLM 不可用（未配置或模型不支持视觉）时**优雅降级**：记录警告并保留原 content，不中断同步/分析。
- 测试与文档同步更新。

## Capabilities

### New Capabilities
- `document-content-extraction`: 文档正文抽取策略--文本层优先、质量评估、视觉 LLM 兜底，保证扫描件/损坏字体 PDF 也能提取可分析正文，并记录抽取来源。

### Modified Capabilities
<!-- 无。正文抽取目前未在任何 spec 中作为明确需求记录（analysis-result-presentation 仅覆盖元数据与图表抽取），故作为新能力引入。 -->

## Impact

- **后端**：`services/info_source/local_folder.py`（质量评估 + 视觉兜底渲染调用）、`services/analysis/llm_client.py`（多模态消息）、`services/info_source/sync.py`（backfill 触发视觉重抽）、`models/info_source.py`（新增 `extraction_method` 字段）、`core/config.py` 与 `config/app.json`（新配置项）、`requirements.txt`（无新依赖，复用 PyMuPDF + httpx）。
- **API**：`InfoItem` 透出字段新增 `extraction_method`（只读展示），无破坏性变更。
- **依赖**：无新系统级依赖；PyMuPDF 1.25.2 已支持 `get_pixmap` 页面渲染；视觉能力复用现有 OpenAI 兼容 LLM endpoint。
- **成本**：视觉兜底按页消耗 LLM token，受 `max_ocr_pages` 上限约束，默认关闭式可控（配置开关）。
- **测试**：扩展 `tests/unit/test_local_folder_extraction.py`、`tests/unit/test_engine.py`/`test_adapters.py`，新增 `LLMClient` 视觉消息单测。
- **文档**：`README.md`、需求规格说明书、设计说明书、`Jenkinsfile`（无结构变化）。
