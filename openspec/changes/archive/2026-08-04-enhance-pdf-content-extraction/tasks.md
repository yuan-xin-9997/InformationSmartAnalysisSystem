## 1. 配置与数据模型

- [x] 1.1 在 `core/config.py` 与 `config/app.json` 新增 `extraction` 节（`vision_fallback`、`vision_model`、`max_ocr_pages`、`min_text_length`、`readable_ratio`、`render_dpi`），支持 `ISAS_EXTRACTION_*` 环境变量覆盖；扩展 `tests/unit/test_config.py` 覆盖默认值与 env 覆盖
- [x] 1.2 `models/info_source.py` 的 `InfoItem` 新增 `extraction_method: str | None` 列；在数据库初始化处加幂等迁移（`ALTER TABLE info_items ADD COLUMN extraction_method TEXT`，列已存在则跳过）；单测验证列存在且老行 NULL

## 2. LLMClient 视觉能力

- [x] 2.1 先写测试 `tests/unit/test_llm_client.py`：`chat_with_images` 构造 OpenAI 视觉消息（`image_url` + `data:image/png;base64,`）、复用超时重试、4xx/格式异常抛 `LLMError`；`chat` 纯文本行为不变
- [x] 2.2 在 `services/analysis/llm_client.py` 实现 `chat_with_images(system, user_text, images, mime="image/png") -> str`，复用现有 base_url/api_key/超时/重试；不改动 `chat`

## 3. 文本质量评估

- [x] 3.1 先写测试：可读字符占比与最小长度判定--空串、乱码符号汤（占比低）、正常中英文（占比高）、过短文本、符号密集文本
- [x] 3.2 在 `local_folder.py` 实现可读字符判定（CJK+拉丁+数字+常用标点）与 `_text_quality_ok(text, min_length, ratio)` 阈值函数

## 4. PDF 视觉兜底抽取

- [x] 4.1 先写测试 `tests/unit/test_local_folder_extraction.py`：文本层可用->`text_layer` 不调视觉；扫描件空文本+启用->渲染并调 `chat_with_images`->`vision_llm`；`max_ocr_pages` 截断并记日志；`vision_model` 独立配置；视觉失败->降级 `extraction_method=none` 且不抛异常；兜底关闭->仅文本层
- [x] 4.2 实现视觉兜底：`page.get_pixmap(dpi=...)` 渲染 PNG、逐页 `chat_with_images` 提取文本、按页序拼接、`extraction_method` 赋值、`try/except` 优雅降级、`max_ocr_pages` 截断日志
- [x] 4.3 `_extract_full` 把 `extraction_method` 经 `InfoItemData.extra` 透传；`extract_text` 返回值结构适配（文本层文本 + 抽取方式）

## 5. 同步与重抽集成

- [x] 5.1 测试 + 实现 `sync.py`：`_apply_metadata`/新建与更新分支写入 `extraction_method`；backfill 选择条件扩展为纳入 `extraction_method IS NULL/='none'` 或 `content` 为空的条目；重抽后 `analyzed=False`
- [x] 5.2 测试 + 实现 `reextract_item`：手动重抽走文本层+视觉兜底，更新 `content` 与 `extraction_method`，`analyzed=False`

## 6. API 透出

- [x] 6.1 `InfoItem` 相关 schema 与分析结果接口只读返回 `extraction_method`；扩展 `tests/unit/test_analysis_results_api.py` 验证字段透出

## 7. 文档与部署验证

- [x] 7.1 更新 `README.md`：新增 `extraction` 配置说明、视觉兜底机制、部署注意事项（视觉兜底需多模态模型，可配独立 `vision_model`）
- [x] 7.2 更新需求规格说明书、设计说明书中正文抽取相关章节
- [x] 7.3 确认 `Jenkinsfile` 与 systemd 配置无结构变化（无新依赖、无新端口/路径）
- [x] 7.4 运行全量 `pytest`（unit + smoke）通过；提交后触发 Jenkins 手工构建并由用户验证
