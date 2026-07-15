"""Local-folder information-source adapter."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from .base import InfoItemData, InfoSourceAdapter, SourceStatus


def extract_text(path: Path) -> str | None:
    """Extract plain text from a file based on its extension."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix in (".html", ".htm"):
            html = path.read_text(encoding="utf-8", errors="ignore")
            return BeautifulSoup(html, "lxml").get_text("\n", strip=True)
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix == ".docx":
            return _extract_docx(path)
    except Exception:
        return None
    return None


def _extract_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n".join(parts).strip()


def _extract_docx(path: Path) -> str:
    import docx

    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()


class LocalFolderAdapter(InfoSourceAdapter):
    type = "local_folder"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.folder_path: Path = Path(config["folder_path"])
        self.patterns: list[str] = config.get("patterns") or [
            "*.txt",
            "*.md",
            "*.pdf",
            "*.docx",
            "*.html",
        ]
        self.recursive: bool = bool(config.get("recursive", True))
        self.max_items: int = int(config.get("max_items") or 50)

    @staticmethod
    def required_config_keys() -> list[str]:
        return ["folder_path"]

    def _iter_files(self):
        if not self.folder_path.exists():
            return
        glob = self.folder_path.rglob if self.recursive else self.folder_path.glob
        for pattern in self.patterns:
            for f in glob(pattern):
                if f.is_file():
                    yield f

    def check_status(self) -> SourceStatus:
        if not self.folder_path.exists():
            return SourceStatus(ok=False, message=f"文件夹不存在: {self.folder_path}")
        count = sum(1 for _ in self._iter_files())
        return SourceStatus(ok=True, message=f"共 {count} 个匹配文件", item_count=count)

    def fetch_new_items(self, since: datetime | None = None) -> list[InfoItemData]:
        items: list[InfoItemData] = []
        for f in self._iter_files():
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if since and mtime <= since:
                continue
            content = extract_text(f)
            if content is None:
                continue
            items.append(
                InfoItemData(
                    external_id=str(f.resolve()),
                    title=f.name,
                    url=str(f),
                    content=content,
                    published_at=mtime,
                )
            )
            if len(items) >= self.max_items:
                break
        return items
