## Context

项目级 CLAUDE.md 新增两条架构要求：OCR 需求优先用 NAS 本地 OCR 服务（ollama / `glm-ocr`，`http://192.168.0.100:11980`，`POST /v1/ocr`），翻译需求优先用 NAS 本地翻译服务（ollama / `translategemma`，`http://192.168.0.100:11880`，`POST /v1/translate`）。

当前 PDF 正文抽取的"视觉兜底"实现见 `src/app/backend/services/info_source/local_folder.py::_vision_extract_pdf`：文本层质量不佳时，用 PyMuPDF 把每页渲染成 PNG，逐页调用 `LLMClient.chat_with_images`（通用 OpenAI 兼容多模态 LLM）提取文本，按页序拼接，`extraction_method` 记为 `vision_llm`。该路径依赖 `llm.api_key`（OpenAI），而 `config/app.json` 中该 Key 仍为占位符 `sk-请替换为真实Key`，`LLMClient.__init__` 会显式抛 `LLMError`，故兜底实际不可用。系统当前没有任何翻译相关代码。

两个本地服务的接口已探明：
- OCR `POST /v1/ocr`：multipart 表单，字段 `file`（必填，octet-stream）、`mode`（`text`/`markdown`/`table`/`formula`，默认 `text`）、`language`（默认 `auto`）；响应 `OcrResponse` 含 `text`、`pages`、`page_results[{page,text}]`、`processing_seconds`。
- 翻译 `POST /v1/translate`：JSON，字段 `text`（必填）、`source`（默认 `auto`）、`target`（默认 `zh-Hans`）、`mode`（`quality`/`fast`，默认 `quality`）、`format`（`text`/`markdown`，默认 `text`）；响应 `TranslateResponse` 含 `translation`、`model`、`source`、`target`、`mode`、`chunks`。
- 鉴权：`Authorization: Bearer <api_key>`（与现有 `webfetch_client` 一致；翻译服务实测 Bearer 可用、无认证返回 401。OCR 服务与翻译服务同属一套 NAS 服务网关，Bearer 鉴权方式一致，实现时用健康检查 + 一次冒烟调用确认）。

约束（来自 CLAUDE.md / 项目规范）：禁止硬编码 IP/端口/Key（一律可配置，支持环境变量覆盖）；复用现有 `httpx`，不引新依赖；优雅降级不得中断同步/分析。

## Goals / Non-Goals

**Goals:**
- 将 PDF 视觉兜底切换为调用本地 OCR 服务，使兜底在无外部 OpenAI Key 时即可工作（自托管、零外部依赖）。
- 新增本地翻译服务客户端与配置（`TranslationClient` + `translate` 配置块），提供可调用能力，本轮不接入业务流程（经用户确认范围）。
- 保持"先文本层、后兜底"与优雅降级语义不变；`max_ocr_pages`、DPI、质量阈值等既有配置沿用。
- 配置与代码符合项目规范：可配置、可经环境变量覆盖、不硬编码环境信息。

**Non-Goals:**
- 不把翻译接入分析流程或信息源 ingestion（后续单独变更）。
- 不改动 PDF 文本层抽取与质量评估逻辑（`_extract_pdf` / `_text_quality_ok`）。
- 不迁移历史 `extraction_method='vision_llm'` 记录（兼容保留，无需 DB 迁移）。
- 不替换通用分析 LLM（`llm` 配置块与 `LLMClient` 保留，供 `engine.py` 分析使用）。
- 不评估 OCR 服务是否直接接受整份 PDF（per-page 图片方案优先；整 PDF 直传留作未来优化）。

## Decisions

### D1. 新增 `services/clients/` 包存放 OCR / 翻译客户端
新建 `src/app/backend/services/clients/`（`__init__.py` + `ocr_client.py` + `translation_client.py`），与现有 `llm_client.py`（在 `analysis/`）、`webfetch_client.py`（在 `info_source/`）并列但独立成包。
- **理由**：OCR 与翻译都是"调用外部 HTTP 服务"的薄客户端，无领域归属；翻译本轮无调用方，放进 `info_source/` 会成为孤儿，放进 `analysis/` 语义不符。独立 `clients/` 包便于发现与后续扩展。
- **备选**：把 `ocr_client.py` 放 `info_source/`（唯一调用方在 `local_folder.py`）——拒绝，理由如上；或把所有外部客户端统一迁入 `clients/`（含 `llm_client`/`webfetch_client`）——拒绝，超出本次范围、徒增 diff。

### D2. OCR 调用粒度：逐页渲染 PNG → `POST /v1/ocr`
保留现有"PyMuPDF `get_pixmap(dpi=render_dpi)` 渲染每页为 PNG"逻辑，把每页 PNG 以 multipart `file` 字段发往 `/v1/ocr`（`mode=text`、`language=auto`），取响应 `.text`（或 `page_results[0].text`），按页序拼接。
- **理由**：与现有逐页调用结构同构，最小改动；不依赖 OCR 服务是否支持整份 PDF；`max_ocr_pages` 截断逻辑天然复用。
- **备选**：整份 PDF 直传 `/v1/ocr`（若服务支持，可省去本地渲染）——推迟；实测整 PDF 直传超时未返回（glm-ocr 冷启动），且是否支持多页未确认，留作未来优化。
- **超时**：glm-ocr 首次推理冷启动较慢（实测 60s 未返回），`ocr.timeout_seconds` 默认设为 **120**（per-page），可配置。

### D3. 鉴权与请求头
两客户端统一 `Authorization: Bearer <api_key>`，与 `webfetch_client` 一致。OCR 文件上传用 `httpx` 的 `files={"file": (filename, img_bytes, "image/png")}` + `data={"mode": "text", "language": "auto"}`；翻译用 `json={...}`。
- **验证**：翻译服务实测 Bearer 200、无认证 401；OCR 服务 Bearer 鉴权方式同网关一致，实现时以健康检查 + 一次冒烟调用确认（若返回 401/403 则尝试 `X-API-Key`，并在任务中记录）。

### D4. `extraction_method` 枚举扩展为 `ocr_service`
新抽取记录的兜底来源记为 `ocr_service`（取代 `vision_llm`）；DB 中历史 `vision_llm` 值兼容保留，不迁移。
- **理由**：命名诚实反映"调用专用 OCR 服务"而非"通用多模态 LLM"；`sync.py` 重抽逻辑只判 `extraction_method == 'none'`（已核实），不依赖 `vision_llm`，故安全。
- **备选**：保留 `vision_llm` 值仅换后端——拒绝，值与机制不符，且 spec 文案需改。

### D5. 配置：新增 `ocr` / `translate` 块，废弃 `extraction.vision_model`
`config/app.json` 新增：
```json
"ocr": { "base_url": "http://192.168.0.100:11980", "api_key": "c20d...da06", "timeout_seconds": 120, "mode": "text", "language": "auto" },
"translate": { "base_url": "http://192.168.0.100:11880", "api_key": "4868...9c4a", "timeout_seconds": 60, "default_target": "zh-Hans", "default_mode": "quality" }
```
`core/config.py` 新增 `ocr_*` / `translate_*` 字段，环境变量前缀 `ISAS_OCR_*` / `ISAS_TRANSLATE_*`。`extraction.vision_model`（`extraction_vision_model` / `ISAS_EXTRACTION_VISION_MODEL`）标记废弃：保留键读取以向后兼容（不抛错），但 `_vision_extract_pdf` 不再使用。
- **理由**：与 `web_fetch` / `llm` 配置块风格一致；`vision_model` 仅服务于旧 LLM 兜底，新方案模型由 OCR 服务自管。

### D6. 优雅降级语义对齐
`OCRClient` 未配置（`base_url`/`api_key` 为空）、健康检查失败、或调用错误/超时时，`_vision_extract_pdf` 捕获并记 warning，返回空串，外层记 `extraction_method='none'` 并保留文本层 `content`，不抛异常、不中断同步/分析——与现有 `LLMError` 降级路径一致。`TranslationClient` 本轮无调用方，其错误以 `TranslationError` 抛出供未来调用方处理。

## Risks / Trade-offs

- **[OCR 服务冷启动慢 / 不可用]** → 默认超时 120s/页；服务不可用时优雅降级为 `none`；`max_ocr_pages=10` 限制总耗时。大 PDF 兜底耗时可接受但需日志可观测。
- **[逐页 N 次 HTTP 调用]** → 与现状一致（原本逐页 LLM 调用），无回归；未来若服务支持整 PDF 直传可优化。
- **[鉴权头不确定]** → 翻译已实测 Bearer；OCR 实现时冒烟验证，必要时回退 `X-API-Key`（任务中记录）。
- **[翻译客户端本轮无调用方 = 暂存死代码]** → 经用户确认为预期范围；用单测覆盖，避免腐化。
- **[废弃 `extraction.vision_model` 配置]** → 保留键读取避免旧 `app.json` 启动失败；仅停止使用，无破坏性。
- **[IP 直连失败]** → CLAUDE.md 指明可回退公网域名（`https://ocr.yuan-xin.top` / `https://translate.yuan-xin.top`）；`base_url` 可配置即可覆盖，无需代码特殊处理。

## Migration Plan

1. **配置**：`config/app.json` 新增 `ocr` / `translate` 块（部署时不覆盖既有 `app.json`，按项目规范增量合并）；`extraction.vision_model` 保留不动。
2. **部署**：更新代码（新客户端 + `local_folder.py` 改写 + `config.py`）后重启服务；新同步的扫描件 PDF 走 OCR 服务，`extraction_method='ocr_service'`。
3. **历史数据**：无需迁移；历史 `vision_llm` 记录兼容保留，前端/邮件按原值展示。
4. **回滚**：将 `extraction.vision_fallback` 置 `false` 可立即关闭兜底（回退纯文本层）；或回退代码版本。`ocr.api_key` 留空也会触发降级。
5. **验证**：健康检查 `GET /health`；用一份扫描件 PDF 触发 `reextract_item`，确认 `extraction_method` 变为 `ocr_service` 且 `content` 非空。

## Open Questions

- OCR 服务 Bearer 鉴权是否与翻译一致？（实现时冒烟验证；预期一致。）
- OCR 服务是否支持整份 PDF 直传以省去本地渲染？（推迟；当前 per-page 方案已可用。）
- 翻译客户端未来接入点（分析前翻译外文内容？ingestion 落库翻译？）——本轮不决，后续变更再定。
