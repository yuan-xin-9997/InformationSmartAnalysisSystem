## Why

项目级 CLAUDE.md 新增两条架构要求：OCR 需求优先使用 NAS 本地 OCR 服务（ollama / `glm-ocr`，`http://192.168.0.100:11980`），翻译需求优先使用 NAS 本地翻译服务（ollama / `translategemma`，`http://192.168.0.100:11880`）。当前系统 PDF 正文抽取的"视觉兜底"走的是通用 OpenAI 兼容多模态 LLM（`LLMClient.chat_with_images`），依赖外部 OpenAI Key——而 `config/app.json` 中该 Key 仍为占位符，兜底实际不可用，且与新项目标准不符；同时系统尚无任何翻译能力。本次变更将视觉兜底切换到本地 OCR 服务（自托管、零外部依赖、即开即用），并新增本地翻译服务客户端与配置，为后续翻译需求打好基础。

## What Changes

- 新增 OCR 服务客户端 `OCRClient`，调用本地 OCR 服务 `POST /v1/ocr`（multipart 表单，`Authorization: Bearer <api_key>`），逐页渲染图片识别文本。
- 将 `local_folder.py::_vision_extract_pdf` 的兜底实现从 `LLMClient.chat_with_images` 迁移到 `OCRClient`；`extraction_method` 新增值 `ocr_service`（取代新抽取记录的 `vision_llm`；历史 `vision_llm` 值保留兼容，不强制迁移）。
- 新增翻译服务客户端 `TranslationClient`，调用本地翻译服务 `POST /v1/translate`（JSON，Bearer 鉴权），**仅提供客户端与配置**，本轮不接入任何业务流程（经用户确认）。
- 配置新增 `ocr` 与 `translate` 两个配置块（`base_url` / `api_key` / `timeout_seconds` 等，均可经环境变量覆盖）；`extraction.vision_model` 配置项废弃（OCR 服务自管模型）。
- 兜底仍保持"先文本层、后兜底"与优雅降级（OCR 服务不可用时记 `extraction_method = none` 并告警），`max_ocr_pages` 渲染页数上限沿用。

## Capabilities

### New Capabilities
- `translation-service`: 本地翻译服务客户端与配置——封装 `POST /v1/translate`，提供 `text` / `source` / `target` / `mode` / `format` 参数与超时/错误处理；本轮不接入业务流程，仅提供可调用能力与配置。

### Modified Capabilities
- `document-content-extraction`: 视觉兜底正文抽取的执行后端由"通用多模态 LLM（`chat_with_images`）"改为"本地 OCR 服务（`POST /v1/ocr`）"；`extraction_method` 枚举新增 `ocr_service`（新抽取记录使用，取代 `vision_llm`）；`extraction.vision_model` 配置项废弃。

## Impact

- **代码**：
  - `src/app/backend/services/info_source/local_folder.py`——`_vision_extract_pdf` 兜底实现重写（调用 `OCRClient` 代替 `LLMClient.chat_with_images`），`extraction_method` 返回值由 `vision_llm` 改为 `ocr_service`。
  - 新增 `src/app/backend/services/clients/ocr_client.py` 与 `translation_client.py`（与 `llm_client` / `webfetch_client` 并列的外部服务客户端包）。
  - `src/app/backend/core/config.py`——新增 `ocr` / `translate` 配置块，废弃 `extraction_vision_model`。
  - `src/app/backend/models/info_source.py`、`src/app/backend/schemas/info_source.py`——`extraction_method` 取值注释更新为 `text_layer | ocr_service | vision_llm(历史) | none`。
- **配置**：`config/app.json` 新增 `ocr`、`translate` 块；`extraction.vision_model` 标记废弃（保留键以向后兼容，不再读取）。
- **API / 数据**：`extraction_method` 枚举扩展；DB 中已存 `vision_llm` 历史值兼容保留，`sync.py` 仅按 `none` 判断重抽逻辑，不受影响。
- **依赖**：复用现有 `httpx`；OCR 走 multipart 文件上传，无新增第三方依赖。
- **测试**：更新 `tests/unit/test_local_folder_extraction.py`、`tests/unit/test_config.py`；新增 `OCRClient` / `TranslationClient` 单测（mock HTTP）。
- **文档**：README、需求规格说明书、设计说明书更新本地 OCR / 翻译服务说明与配置项。
