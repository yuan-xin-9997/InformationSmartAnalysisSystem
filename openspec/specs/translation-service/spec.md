# translation-service Specification

## Purpose
封装 NAS 本地翻译服务（ollama / `translategemma`）的客户端与配置，提供可调用的文本翻译能力（默认译为简体中文 `zh-Hans`，支持 `quality` / `fast` 模式）。本轮仅提供客户端与配置，未接入业务流程，供后续翻译需求（如分析前外文内容翻译）集成。
## Requirements
### Requirement: 本地翻译服务客户端

系统 SHALL 提供翻译客户端（`TranslationClient`），封装 NAS 本地翻译服务的 `POST /v1/translate` 接口：使用 `Authorization: Bearer <api_key>` 鉴权，请求体为 JSON，包含 `text`（必填）、`source`（默认 `auto`）、`target`（默认 `zh-Hans`）、`mode`（`quality` / `fast`，默认 `quality`）、`format`（`text` / `markdown`，默认 `text`）字段；从响应 JSON 的 `translation` 字段返回译文文本。客户端 SHALL 在 `base_url` / `api_key` 未配置时于构造期抛出 `TranslationError`，在 HTTP 非 2xx、网络错误或超时时抛出 `TranslationError` 且不返回部分结果。本轮客户端 SHALL 不接入任何业务流程（分析、信息源同步均不调用），仅作为可调用能力与配置存在，供后续变更集成。

#### Scenario: 成功翻译文本
- **WHEN** 调用 `TranslationClient.translate("Hello world", target="zh-Hans", mode="fast")` 且翻译服务可用
- **THEN** 客户端以 Bearer 鉴权向 `POST /v1/translate` 发送 JSON 请求，返回服务端的 `translation` 译文文本

#### Scenario: 服务端错误时抛异常
- **WHEN** 翻译服务返回 HTTP 5xx 或网络错误/超时
- **THEN** 客户端抛出 `TranslationError`，不返回部分译文

#### Scenario: 未配置时构造失败
- **WHEN** `translate.base_url` 或 `translate.api_key` 为空时构造 `TranslationClient`
- **THEN** 客户端于构造期抛出 `TranslationError`，提示配置缺失

### Requirement: 翻译服务配置

系统 SHALL 通过 `config/app.json` 的 `translate` 配置块管理本地翻译服务连接与默认参数，包含 `base_url`、`api_key`、`timeout_seconds`（默认 60）、`default_target`（默认 `zh-Hans`）、`default_mode`（默认 `quality`）；所有字段 MUST 支持以 `ISAS_TRANSLATE_*` 环境变量覆盖（`ISAS_TRANSLATE_BASE_URL`、`ISAS_TRANSLATE_API_KEY`、`ISAS_TRANSLATE_TIMEOUT`、`ISAS_TRANSLATE_DEFAULT_TARGET`、`ISAS_TRANSLATE_DEFAULT_MODE`）。当 `base_url` IP 访问失败时，运维可通过修改 `base_url` 为公网域名（`https://translate.yuan-xin.top`）回退，系统 MUST NOT 硬编码该地址。该配置 MUST 在系统配置模块中只读可见。

#### Scenario: 环境变量覆盖配置
- **WHEN** 设置 `ISAS_TRANSLATE_BASE_URL` 与 `ISAS_TRANSLATE_API_KEY` 环境变量
- **THEN** `TranslationClient` 使用环境变量指定的地址与密钥，而非 `app.json` 中的值

#### Scenario: 默认参数生效
- **WHEN** 调用 `TranslationClient.translate(text)` 且未显式传 `target` / `mode`
- **THEN** 客户端使用配置块的 `default_target`（默认 `zh-Hans`）与 `default_mode`（默认 `quality`）

#### Scenario: 配置在系统配置页可见
- **WHEN** 管理员查看系统配置模块
- **THEN** `translate` 配置块的字段（脱敏 `api_key`）只读可见

