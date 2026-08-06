# Implementation Tasks

## 1. 配置层

- [x] 1.1 在 `src/app/backend/core/config.py` 新增 `ocr` 配置块字段：`ocr_base_url` / `ocr_api_key` / `ocr_timeout_seconds`（默认 120）/ `ocr_mode`（默认 `text`）/ `ocr_language`（默认 `auto`），均支持 `ISAS_OCR_*` 环境变量覆盖
- [x] 1.2 在 `src/app/backend/core/config.py` 新增 `translate` 配置块字段：`translate_base_url` / `translate_api_key` / `translate_timeout_seconds`（默认 60）/ `translate_default_target`（默认 `zh-Hans`）/ `translate_default_mode`（默认 `quality`），均支持 `ISAS_TRANSLATE_*` 环境变量覆盖
- [x] 1.3 标记 `extraction_vision_model` / `ISAS_EXTRACTION_VISION_MODEL` 废弃：保留读取以向后兼容（不抛错），加注释说明不再使用
- [x] 1.4 在 `src/config/app.json` 新增 `ocr` 与 `translate` 配置块（写入 NAS 地址与 API Key 及默认值）；`extraction.vision_model` 保留不动
- [x] 1.5 确认系统配置页对 `ocr.api_key` / `translate.api_key` 脱敏显示（沿用既有 `web_fetch` / `llm` 的 api_key 脱敏逻辑；若无通用脱敏则补齐）
- [x] 1.6 更新 `src/tests/unit/test_config.py`：断言 `ocr` / `translate` 字段默认值、`ISAS_OCR_*` / `ISAS_TRANSLATE_*` 环境变量覆盖、`extraction_vision_model` 仍可读取但不影响新逻辑

## 2. OCR 服务客户端

- [x] 2.1 新建 `src/app/backend/services/clients/__init__.py` 与 `ocr_client.py`，实现 `OCRClient` 与 `OCRError`：`Authorization: Bearer <api_key>` 鉴权，multipart 上传 PNG（`files={"file": (filename, img_bytes, "image/png")}` + `data={"mode","language"}`），从响应 JSON 取 `text` 返回
- [x] 2.2 `OCRClient.__init__` 在 `base_url` / `api_key` 为空时抛 `OCRError`；`ocr(image_bytes, filename=None, mode=None, language=None) -> str` 在 HTTP 非 2xx / 网络错误 / 超时时抛 `OCRError`，不返回部分结果
- [x] 2.3 （可选）实现 `OCRClient.health() -> bool` 调 `GET /health`，供启动/冒烟检查
- [x] 2.4 新增 `src/tests/unit/test_ocr_client.py`：mock httpx 验证成功返回文本、HTTP 错误抛 `OCRError`、超时抛 `OCRError`、未配置构造失败

## 3. 翻译服务客户端

- [x] 3.1 新建 `src/app/backend/services/clients/translation_client.py`，实现 `TranslationClient` 与 `TranslationError`：Bearer 鉴权，JSON `POST /v1/translate`（`text` / `source` / `target` / `mode` / `format`），从响应 JSON 取 `translation` 返回
- [x] 3.2 `__init__` 未配置抛 `TranslationError`；`translate(text, source="auto", target=None, mode=None, format="text") -> str`，`target`/`mode` 缺省时取 `translate_default_target` / `translate_default_mode`；HTTP 错误/超时抛 `TranslationError`
- [x] 3.3 新增 `src/tests/unit/test_translation_client.py`：mock httpx 验证成功译文、错误抛 `TranslationError`、未配置构造失败、默认 target/mode 生效

## 4. PDF 兜底迁移到 OCR 服务

- [x] 4.1 改写 `src/app/backend/services/info_source/local_folder.py::_vision_extract_pdf`：用 `OCRClient` 逐页上传渲染后的 PNG 调 `/v1/ocr`，取每页 `text` 按页序拼接；移除 `LLMClient` / `chat_with_images` / `vision_model` 相关逻辑
- [x] 4.2 `_extract_pdf_content` 兜底成功返回值由 `"vision_llm"` 改为 `"ocr_service"`；OCR 客户端未配置 / `OCRError` 时 `_vision_extract_pdf` 返回空串（外层记 `extraction_method="none"` 并保留文本层 content）
- [x] 4.3 保留 `max_ocr_pages` 截断（含日志）、`render_dpi`、逐页失败跳过、渲染失败降级等既有语义
- [x] 4.4 更新 `src/tests/unit/test_local_folder_extraction.py`：mock `OCRClient` 验证 `ocr_service` 成功路径、OCR 未配置/失败降级为 `none`、页数超限截断

## 5. 模型 / Schema / 前端注释

- [x] 5.1 更新 `src/app/backend/models/info_source.py` 与 `src/app/backend/schemas/info_source.py` 中 `extraction_method` 取值注释为 `text_layer | ocr_service | vision_llm(历史) | none`
- [x] 5.2 检索前端（`src/app/frontend/src`）是否对 `extraction_method` 做标签映射；若存在，新增 `ocr_service` 标签（如"OCR 兜底"）并保留 `vision_llm` 历史标签；若无映射则跳过

## 6. 集成与冒烟验证

- [x] 6.1 启动服务，确认 OCR / 翻译服务 `GET /health` 可达（IP 不通时改 `base_url` 为公网域名 `https://ocr.yuan-xin.top` / `https://translate.yuan-xin.top`）
- [x] 6.2 冒烟：对一份扫描件 PDF 触发 `reextract_item`，确认 `extraction_method` 变为 `ocr_service` 且 `content` 非空
- [x] 6.3 冒烟：手动调用 `TranslationClient.translate(...)` 验证返回中文译文
- [x] 6.4 运行全量单元测试（`pytest src/tests`），全部通过

## 7. 文档与部署

- [x] 7.1 更新 `README.md`：新增本地 OCR / 翻译服务说明、`ocr` / `translate` 配置项与环境变量章节
- [x] 7.2 更新需求规格说明书、设计说明书：OCR 兜底切换为本地 OCR 服务、新增翻译服务客户端章节
- [x] 7.3 更新 `Jenkinsfile`（若涉及配置/部署步骤）；确认部署不覆盖既有 `config/app.json`（仅增量合并新键）
- [x] 7.4 提交 GitHub 后手动触发 Jenkins 手工构建，访问服务验证 OCR 兜底与翻译客户端符合预期
