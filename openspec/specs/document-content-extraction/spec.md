# document-content-extraction Specification

## Purpose
TBD - created by archiving change enhance-pdf-content-extraction. Update Purpose after archive.
## Requirements
### Requirement: PDF 正文文本层抽取与质量评估

系统 SHALL 在抽取 `local_folder` 的 PDF 文件时，优先用 PyMuPDF 文本层（`page.get_text()`）抽取正文。系统 MUST 对文本层结果做质量评估：当结果为空、长度低于阈值（默认 50 字符）、或可读字符占比低于阈值（默认 60%）时，判定文本层不可用。可读字符定义为 CJK 统一汉字、拉丁字母、数字与常用标点；占比 = 可读字符数 / 非空白字符总数。质量阈值（最小长度、可读占比）MUST 可配置。

#### Scenario: 文本层可用时直接采用
- **WHEN** 同步一个原生数字 PDF，其 `page.get_text()` 返回足够长且可读占比高于阈值的文本
- **THEN** 系统以文本层结果作为 `InfoItem.content`，`extraction_method` 记为 `text_layer`，不调用视觉 LLM

#### Scenario: 扫描件文本层为空触发兜底
- **WHEN** 同步一个扫描件/图片型 PDF，其 `page.get_text()` 返回空串
- **THEN** 系统判定文本层不可用并启用视觉 LLM 兜底抽取

#### Scenario: 乱码文本层触发兜底
- **WHEN** 同步一个字体编码损坏的 PDF，其 `page.get_text()` 返回可读字符占比低于阈值的乱码
- **THEN** 系统判定文本层不可用并启用视觉 LLM 兜底抽取

### Requirement: 视觉 LLM 兜底正文抽取

当文本层不可用且视觉兜底启用时，系统 SHALL 用 PyMuPDF `page.get_pixmap()` 把 PDF 页面渲染为图片（可配置 DPI，默认 150），逐页调用 NAS 本地 OCR 服务（`POST /v1/ocr`，基于视觉 LLM `glm-ocr`，`Authorization: Bearer <api_key>` 鉴权，multipart 上传该页 PNG，`mode` 默认 `text`、`language` 默认 `auto`）提取该页正文文本，取响应 `text` 字段，按页序拼接为整篇 `content` 落库。渲染页数 MUST 受可配置上限（默认 10 页）约束，超限时截断并在日志记录已截断。兜底所用 OCR 模型由 OCR 服务自管，系统 MUST NOT 再配置兜底视觉模型；`extraction.vision_model` 配置项废弃（保留键以向后兼容，不再读取）。兜底抽取产生的 `content` MUST 为纯文本，沿用既有"先抽取、后分析"流程，分析侧无感知。

#### Scenario: 渲染页面并视觉提取正文
- **WHEN** 文本层不可用且视觉兜底启用
- **THEN** 系统把各页渲染成 PNG 图片，逐页以 multipart 上传至本地 OCR 服务 `POST /v1/ocr` 提取文本，按页序拼接后作为 `content`，`extraction_method` 记为 `ocr_service`

#### Scenario: 页数超上限时截断并记录
- **WHEN** 一个 30 页扫描件 PDF 且最大渲染页数配置为 10
- **THEN** 系统只对前 10 页做 OCR 抽取，并在日志记录已截断

#### Scenario: 视觉模型可独立配置
- **WHEN** 配置了 `extraction.vision_model`（旧视觉兜底模型配置）
- **THEN** 视觉兜底改用本地 OCR 服务，模型由服务自管（`glm-ocr`）；`extraction.vision_model` 已废弃、被忽略，不影响兜底调用

### Requirement: 正文抽取方式记录与追溯

`InfoItem` SHALL 新增 `extraction_method` 字段（取值 `text_layer` / `ocr_service` / `none`；历史记录可能存在 `vision_llm`，兼容保留不迁移），记录该条目正文的抽取来源。文本层可用时记 `text_layer`；视觉兜底（本地 OCR 服务）成功产出非空文本时记 `ocr_service`；两者均未产出有效文本时记 `none`。该字段 MUST 在分析结果接口只读返回，便于在前端与邮件中追溯正文来源。

#### Scenario: 记录文本层来源
- **WHEN** 文本层抽取结果通过质量评估
- **THEN** 该 `InfoItem.extraction_method` 记为 `text_layer`

#### Scenario: 记录视觉来源
- **WHEN** 视觉兜底（本地 OCR 服务）成功产出非空正文文本
- **THEN** 该 `InfoItem.extraction_method` 记为 `ocr_service`

#### Scenario: 均未产出有效文本时记录 none
- **WHEN** 文本层不可用且视觉兜底未启用或未产出非空文本
- **THEN** 该 `InfoItem.extraction_method` 记为 `none`，`content` 保留文本层原值（可能为空），同步不中断

### Requirement: 视觉兜底可配置与优雅降级

系统 SHALL 通过配置控制视觉兜底：`config/app.json` 的 `extraction` 节（支持 `ISAS_EXTRACTION_*` 环境变量覆盖）控制启用开关（默认启用）、最大渲染页数、最小文本长度阈值、可读占比阈值、渲染 DPI；`config/app.json` 的 `ocr` 节（支持 `ISAS_OCR_*` 环境变量覆盖）控制本地 OCR 服务连接（`base_url`、`api_key`、`timeout_seconds` 默认 120、`mode` 默认 `text`、`language` 默认 `auto`）。`extraction.vision_model` 配置项废弃。当视觉兜底未启用、OCR 服务未配置（`base_url` / `api_key` 为空）、或 OCR 调用返回错误/超时时，系统 MUST 优雅降级：记录警告日志，保留文本层原 `content`，记 `extraction_method=none`，不抛出异常、不中断同步或分析。

#### Scenario: 关闭兜底时仅用文本层
- **WHEN** `extraction.vision_fallback` 配置为 false
- **THEN** 文本层不可用时直接记 `extraction_method=none`，不调用 OCR 服务

#### Scenario: LLM 未配置时优雅降级
- **WHEN** 视觉兜底启用但 `ocr.base_url` 或 `ocr.api_key` 未配置
- **THEN** 系统记录警告并跳过兜底抽取，`extraction_method=none`，同步继续不报错

#### Scenario: 视觉调用失败时降级
- **WHEN** 本地 OCR 服务调用返回错误或超时
- **THEN** 系统记录警告，`extraction_method=none`，`content` 保留文本层原值，不中断同步

### Requirement: 历史条目重抽走视觉兜底

系统 SHALL 在 `local_folder` 同步的 backfill 流程与 `reextract_item` 手动重抽中，对 `extraction_method` 为 `none` 或 `content` 为空的历史条目，重新走"文本层 + 视觉兜底"流程。重抽后 `content` 与 `extraction_method` MUST 更新；内容变更时沿用既有语义将 `analyzed` 置回 False，以便重新分析。

#### Scenario: backfill 重抽空 content 条目
- **WHEN** 同步 backfill 遇到一个 `content` 为空的历史条目且视觉兜底启用
- **THEN** 系统对其重新抽取并走视觉兜底，更新 `content` 与 `extraction_method`

#### Scenario: 手动重抽乱码条目
- **WHEN** 用户对一条 `extraction_method=none` 的历史条目触发 `reextract`
- **THEN** 系统重新走文本层 + 视觉兜底，`content` 更新为可读文本，`extraction_method` 更新，`analyzed` 置回 False

