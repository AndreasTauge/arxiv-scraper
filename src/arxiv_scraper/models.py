from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Paper:
    """Metadata for one arXiv paper."""

    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    abstract: str
    published: datetime
    updated: datetime
    categories: tuple[str, ...]
    primary_category: str
    url: str
    pdf_url: str | None = None

    def to_dict(self, *, summary: str | None = None) -> dict[str, object]:
        """Return a JSON-serializable representation of the paper."""
        result = asdict(self)
        result["published"] = self.published.isoformat()
        result["updated"] = self.updated.isoformat()
        if summary is not None:
            result["summary"] = summary
        return result
