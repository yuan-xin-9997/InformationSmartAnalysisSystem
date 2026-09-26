"""Website information-source adapter (uses the WebFetch service)."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup

from .base import InfoItemData, InfoSourceAdapter, SourceStatus
from .webfetch_client import WebFetchClient, WebFetchError


def normalize_url(url: str) -> str:
    """Canonical article identity, stripping fragments and tracking parameters."""
    parts = urlsplit(url)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                           if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", query, ""))


def website_sites(config: dict) -> list[dict]:
    if isinstance(config.get("sites"), list):
        return config["sites"]
    return [{"name": config.get("name") or urlsplit(config["url"]).netloc,
             **config}]


class WebsiteAdapter(InfoSourceAdapter):
    type = "website"

    def __init__(self, config: dict, web_fetch_client: WebFetchClient | None = None) -> None:
        super().__init__(config)
        self.url: str = config["url"]
        self.link_selector: str = config.get("link_selector") or "a"
        self.content_selector: str = config.get("content_selector") or "article, main, body"
        self.mode: str = config.get("mode") or "auto"
        self.max_items: int = int(config.get("max_items") or 20)
        self.base_url: str = config.get("base_url") or self.url
        self._client = web_fetch_client or WebFetchClient()

    @staticmethod
    def required_config_keys() -> list[str]:
        return ["url"]

    def check_status(self) -> SourceStatus:
        try:
            html = self._client.fetch_html(self.url, mode=self.mode)
            links = BeautifulSoup(html, "lxml").select(self.link_selector)
            if not any(a.get("href") for a in links):
                return SourceStatus(ok=False, message="栏目页未找到文章链接；可能为拦截页面或链接选择器不匹配")
            return SourceStatus(ok=True, message=f"抓取成功，找到 {len(links)} 个候选链接")
        except WebFetchError as exc:
            return SourceStatus(ok=False, message=str(exc))

    def fetch_new_items(
        self,
        since: datetime | None = None,
        known_ids: set[str] | None = None,
    ) -> list[InfoItemData]:
        # The listing page is re-scanned each sync. ``known_ids`` (already-indexed
        # URLs) are skipped so we only fetch new articles (incremental). ``since``
        # is unused -- websites have no reliable modification timestamp.
        known = known_ids or set()
        html = self._client.fetch_html(self.url, mode=self.mode)
        soup = BeautifulSoup(html, "lxml")

        links: list[tuple[str, str]] = []
        seen: set[str] = set()
        candidate_count = 0
        for a in soup.select(self.link_selector):
            href = a.get("href")
            if not href or href.startswith("#"):
                continue
            candidate_count += 1
            abs_url = normalize_url(urljoin(self.base_url, href))
            if abs_url in seen or abs_url in known:
                continue
            seen.add(abs_url)
            links.append((abs_url, a.get_text(strip=True) or abs_url))
            if len(links) >= self.max_items:
                break

        if not candidate_count:
            raise WebFetchError("栏目页未找到文章链接；可能为拦截页面或链接选择器不匹配")

        items: list[InfoItemData] = []
        for abs_url, fallback_title in links:
            try:
                art_html = self._client.fetch_html(abs_url, mode=self.mode)
            except WebFetchError:
                continue
            art_soup = BeautifulSoup(art_html, "lxml")
            node = art_soup.select_one(self.content_selector)
            content = (
                node.get_text("\n", strip=True)
                if node
                else art_soup.get_text("\n", strip=True)
            )
            title_tag = art_soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else fallback_title
            items.append(
                InfoItemData(
                    external_id=abs_url, title=title, url=abs_url, content=content
                )
            )
        return items
