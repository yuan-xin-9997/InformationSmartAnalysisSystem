"""OpenAI-compatible LLM client (configurable base_url/api_key/model)."""
from __future__ import annotations

from typing import Any

import httpx

from ...core.config import settings
from ...core.logging import get_logger

_logger = get_logger("llm")

# 安全下限：推理模型的 token 预算需覆盖「思考 + 回答」，配置过小会导致思考阶段
# 就耗尽预算、`content` 为空且 `finish_reason="length"`（曾因此发出空正文邮件）。
# 配置值低于该下限时按此值生效，避免陈旧/误配的部署侧配置造成静默的空结果。
MIN_MAX_TOKENS = 4096

# 输出被截断时，以翻倍的 max_tokens 重试一次；此为该重试的上限。
MAX_TOKENS_RETRY_CAP = 32000


class LLMError(RuntimeError):
    pass


class LLMTruncatedError(LLMError):
    """输出被截断（``finish_reason="length"``）且重试后仍不完整。"""


class LLMClient:
    """Calls any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.temperature = (
            temperature if temperature is not None else settings.llm_temperature
        )
        configured_tokens = max_tokens or settings.llm_max_tokens
        if configured_tokens < MIN_MAX_TOKENS:
            _logger.warning(
                "llm.max_tokens=%s 低于安全下限 %s，按 %s 生效"
                "（推理模型需覆盖「思考+回答」，过小会返回空 content 或被截断）",
                configured_tokens,
                MIN_MAX_TOKENS,
                MIN_MAX_TOKENS,
            )
            configured_tokens = MIN_MAX_TOKENS
        self.max_tokens = configured_tokens
        self.timeout = timeout or settings.llm_timeout
        if not self.base_url or not self.api_key:
            raise LLMError("LLM base_url 或 api_key 未配置")
        if self.api_key == "sk-请替换为真实Key":
            raise LLMError(
                "LLM api_key 仍为占位符，请在 config/env.local（推荐，不被部署覆盖）或 config/app.json 配置真实 api_key"
            )
        if not self.api_key.isascii():
            raise LLMError(
                "LLM api_key 含非 ASCII 字符，无法用于 HTTP 认证。"
                "请在 config/env.local（推荐）或 config/app.json 配置真实 api_key"
            )

    def chat(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self._post_chat(messages)

    def chat_with_images(
        self,
        system: str,
        user_text: str,
        images: list[bytes],
        mime: str = "image/png",
    ) -> str:
        """Send a multimodal (vision) request: text + one or more images.

        Uses the OpenAI vision message format (``image_url`` with a base64 data
        URI). ``images`` are raw image bytes (rendered/encoded by the caller).
        Reuses the same model/timeout/retry as ``chat``.
        """
        import base64

        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        data_uri_prefix = f"data:{mime};base64,"
        for img in images:
            b64 = base64.b64encode(img).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"{data_uri_prefix}{b64}"}}
            )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        return self._post_chat(messages)

    def _request_once(
        self, messages: list[dict[str, Any]], max_tokens: int
    ) -> dict[str, Any]:
        """POST ``/chat/completions`` with one retry on timeout; return ``choices[0]``."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # 超时自动重试一次（推理模型对长文本响应较慢，偶发超时可重试）。
        r = None
        for attempt in (1, 2):
            try:
                r = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                break
            except httpx.TimeoutException as exc:
                if attempt == 1:
                    _logger.warning("LLM 请求超时(%.1fs)，重试一次", self.timeout)
                    continue
                raise LLMError(
                    f"LLM 请求超时（{self.timeout}s）：{exc}。"
                    "通常因 endpoint 不可达或响应过慢，请检查 llm.base_url 是否可访问，"
                    "或适当调大 llm.timeout_seconds；长文本 + 推理模型建议 ≥180s。"
                ) from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"调用 LLM 失败: {exc}") from exc
        if r.status_code >= 400:
            raise LLMError(f"LLM 返回 {r.status_code}: {r.text[:300]}")
        try:
            choice = r.json()["choices"][0]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"LLM 响应格式异常: {r.text[:300]}") from exc
        if not isinstance(choice, dict):
            raise LLMError(f"LLM 响应格式异常: {r.text[:300]}")
        return choice

    def _post_chat(self, messages: list[dict[str, Any]]) -> str:
        """调用 LLM 并**校验输出有效性**，返回非空文本。

        校验规则（用于杜绝"把空结果当成成功"）：
        - ``finish_reason == "length"`` 视为输出被截断：以翻倍的 ``max_tokens``
          重试一次（上限 ``MAX_TOKENS_RETRY_CAP``），仍截断则抛
          ``LLMTruncatedError``；
        - ``content`` 为空时回退 ``reasoning_content``（部分推理模型把内容放在该
          字段），两者皆空则抛 ``LLMError``。
        """
        max_tokens = self.max_tokens
        for attempt in (1, 2):
            choice = self._request_once(messages, max_tokens)
            message = choice.get("message")
            if not isinstance(message, dict):
                message = {}
            finish_reason = choice.get("finish_reason")
            raw_content = message.get("content")
            text = raw_content.strip() if isinstance(raw_content, str) else ""

            if finish_reason == "length":
                if attempt == 1:
                    max_tokens = min(max_tokens * 2, MAX_TOKENS_RETRY_CAP)
                    _logger.warning(
                        "LLM 输出被截断(finish_reason=length)，以 max_tokens=%s 重试一次",
                        max_tokens,
                    )
                    continue
                raise LLMTruncatedError(
                    f"LLM 输出被截断且重试后仍不完整（finish_reason=length，"
                    f"max_tokens={max_tokens}）。推理模型的 token 预算需覆盖"
                    "「思考+回答」，请调大 llm.max_tokens（建议 ≥16000，"
                    "可用 ISAS_LLM_MAX_TOKENS 覆盖），或缩短单次分析的输入文本。"
                )

            if text:
                return text

            reasoning = message.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning.strip():
                _logger.warning(
                    "LLM 未返回 content（finish_reason=%s），回退使用 reasoning_content",
                    finish_reason,
                )
                return reasoning.strip()

            raise LLMError(
                f"LLM 返回空内容（finish_reason={finish_reason}）。"
                "该条目判为分析失败；请检查 llm.model 是否为推理模型、"
                "llm.max_tokens 是否过小（建议 ≥16000）。"
            )

        # 循环必然在内部 return 或 raise；此行仅为静态分析兜底。
        raise LLMError("LLM 调用未返回有效内容")
