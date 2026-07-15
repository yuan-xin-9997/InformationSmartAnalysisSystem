"""FreshRSS information-source adapter (Google Reader API)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .base import InfoItemData, InfoSourceAdapter, SourceStatus


class FreshRSSAdapter(InfoSourceAdapter):
    type = "freshrss"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.base_url: str = config["base_url"].rstrip("/")
        self.user: str = config["user"]
        self.api_token: str = config["api_token"]
        self.stream: str = config.get("stream") or "user/-/state/com.google/reading-list"
        self.mark_as_read: bool = bool(config.get("mark_as_read", False))
        self.max_items: int = int(config.get("max_items") or 50)
        self.timeout: int = int(config.get("timeout") or 30)
        self._auth: str | None = None

    @staticmethod
    def required_config_keys() -> list[str]:
        return ["base_url", "user", "api_token"]

    def _get_auth(self) -> str:
        if self._auth:
            return self._auth
        url = f"{self.base_url}/api/greader.php/accounts/ClientLogin"
        r = httpx.post(
            url,
            data={"Email": self.user, "Passwd": self.api_token},
            timeout=self.timeout,
        )
        r.raise_for_status()
        for line in r.text.splitlines():
            if line.startswith("Auth="):
                self._auth = line[len("Auth="):].strip()
                return self._auth
        raise RuntimeError("FreshRSS ClientLogin 未返回 Auth，请检查用户名/API Token")

    def _greader_get(self, path: str, params: dict | None = None) -> dict:
        auth = self._get_auth()
        url = f"{self.base_url}/api/greader.php/{path}"
        r = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"GoogleLogin auth={auth}"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def _greader_post(self, path: str, params: dict | None = None) -> str:
        auth = self._get_auth()
        url = f"{self.base_url}/api/greader.php/{path}"
        r = httpx.post(
            url,
            params=params,
            headers={"Authorization": f"GoogleLogin auth={auth}"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.text

    def check_status(self) -> SourceStatus:
        try:
            self._get_auth()
            return SourceStatus(ok=True, message="FreshRSS 认证成功")
        except Exception as exc:
            return SourceStatus(ok=False, message=str(exc))

    def fetch_new_items(
        self,
        since: datetime | None = None,
        known_ids: set[str] | None = None,
    ) -> list[InfoItemData]:
        known = known_ids or set()
        params: dict = {"n": self.max_items}
        if since:
            params["ot"] = int(since.timestamp())
        data = self._greader_get(f"reader/api/0/stream/contents/{self.stream}", params=params)
        items: list[InfoItemData] = []
        for it in data.get("items", []):
            item_id = str(it.get("id", ""))
            if item_id in known:
                continue  # 已索引，跳过（增量）
            title = it.get("title", "") or ""
            url = None
            for alt in it.get("alternate", []) or []:
                if isinstance(alt, dict) and alt.get("href"):
                    url = alt["href"]
                    break
            raw_content = ""
            content_block = it.get("content") or it.get("summary")
            if isinstance(content_block, dict):
                raw_content = content_block.get("content", "") or ""
            content = (
                BeautifulSoup(raw_content, "lxml").get_text("\n", strip=True)
                if raw_content
                else ""
            )
            published = None
            if it.get("published"):
                published = datetime.fromtimestamp(it["published"], tz=timezone.utc)
            items.append(
                InfoItemData(
                    external_id=item_id,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published,
                )
            )
        if self.mark_as_read:
            try:
                self._greader_post("reader/api/0/mark-all-as-read", params={"s": self.stream})
            except Exception:
                pass
        return items
