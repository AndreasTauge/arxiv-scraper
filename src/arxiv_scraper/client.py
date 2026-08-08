from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from .models import Paper

API_URL = "https://export.arxiv.org/api/query"
DEFAULT_CATEGORIES = ("cs.LG", "cs.AI", "stat.ML", "cs.CL", "cs.CV")
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivError(RuntimeError):
    """Raised when arXiv cannot be queried or its response cannot be parsed."""


Transport = Callable[[urllib.request.Request, float], bytes]


def _default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class ArxivClient:
    """Search arXiv and convert its Atom feed into :class:`Paper` objects."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        user_agent: str = "arxiv-paper-scraper/0.1",
        transport: Transport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or _default_transport

    def search(
        self,
        query: str | None = None,
        *,
        categories: Sequence[str] = DEFAULT_CATEGORIES,
        days: int | None = 7,
        max_results: int = 10,
        sort_by: str | None = None,
        now: datetime | None = None,
    ) -> list[Paper]:
        """Return papers matching keywords, categories, and an optional age window."""
        if not 1 <= max_results <= 100:
            raise ValueError("max_results must be between 1 and 100")
        if days is not None and days < 1:
            raise ValueError("days must be positive or None")
        if not categories and not query:
            raise ValueError("provide at least one category or a query")

        effective_sort = sort_by or ("relevance" if query else "submittedDate")
        if effective_sort not in {"relevance", "submittedDate", "lastUpdatedDate"}:
            raise ValueError("invalid sort_by value")

        search_query = self._build_query(query, categories, days, now=now)
        params = urllib.parse.urlencode(
            {
                "search_query": search_query,
                "start": 0,
                "max_results": max_results,
                "sortBy": effective_sort,
                "sortOrder": "descending",
            }
        )
        request = urllib.request.Request(
            f"{API_URL}?{params}",
            headers={"User-Agent": self.user_agent, "Accept": "application/atom+xml"},
        )

        try:
            payload = self._transport(request, self.timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ArxivError(f"arXiv request failed: {exc}") from exc

        return self.parse_feed(payload)

    @staticmethod
    def _build_query(
        query: str | None,
        categories: Sequence[str],
        days: int | None,
        *,
        now: datetime | None,
    ) -> str:
        clauses: list[str] = []
        clean_categories = [category.strip() for category in categories if category.strip()]
        if clean_categories:
            clauses.append("(" + " OR ".join(f"cat:{item}" for item in clean_categories) + ")")

        if query and query.strip():
            safe_query = query.strip().replace('"', r"\"")
            clauses.append(f'all:"{safe_query}"')

        if days is not None:
            end = now or datetime.now(timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            end = end.astimezone(timezone.utc)
            start = end - timedelta(days=days)
            clauses.append(f"submittedDate:[{start:%Y%m%d%H%M%S} TO {end:%Y%m%d%H%M%S}]")

        return " AND ".join(clauses)

    @staticmethod
    def parse_feed(payload: bytes | str) -> list[Paper]:
        """Parse an arXiv Atom response into papers."""
        try:
            root = ET.fromstring(payload)
            return [ArxivClient._parse_entry(entry) for entry in root.findall(f"{_ATOM}entry")]
        except (ET.ParseError, KeyError, TypeError, ValueError) as exc:
            raise ArxivError(f"invalid arXiv response: {exc}") from exc

    @staticmethod
    def _parse_entry(entry: ET.Element) -> Paper:
        def required_text(name: str) -> str:
            element = entry.find(f"{_ATOM}{name}")
            if element is None or element.text is None:
                raise ValueError(f"entry is missing {name}")
            return _normalize(element.text)

        identifier = required_text("id")
        authors = tuple(
            _normalize(name.text or "")
            for author in entry.findall(f"{_ATOM}author")
            if (name := author.find(f"{_ATOM}name")) is not None and name.text
        )
        categories = tuple(
            category.attrib["term"] for category in entry.findall(f"{_ATOM}category")
        )
        primary = entry.find(f"{_ARXIV}primary_category")
        primary_category = primary.attrib.get("term", "") if primary is not None else ""
        links = entry.findall(f"{_ATOM}link")
        page_url = next(
            (link.attrib["href"] for link in links if link.attrib.get("rel") == "alternate"),
            identifier,
        )
        pdf_url = next(
            (link.attrib["href"] for link in links if link.attrib.get("type") == "application/pdf"),
            None,
        )

        return Paper(
            arxiv_id=re.sub(r"v\d+$", "", identifier.rstrip("/").rsplit("/", 1)[-1]),
            title=_clean_latex(required_text("title")),
            authors=authors,
            abstract=_clean_latex(required_text("summary")),
            published=_parse_datetime(required_text("published")),
            updated=_parse_datetime(required_text("updated")),
            categories=categories,
            primary_category=primary_category,
            url=page_url,
            pdf_url=pdf_url,
        )


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _clean_latex(value: str) -> str:
    """Remove common presentational LaTeX while preserving its readable content."""
    formatting_command = re.compile(
        r"\\(?:textbf|textit|texttt|emph|mathrm|mathbf|mathit|operatorname)\{([^{}]*)\}"
    )
    previous = None
    while value != previous:
        previous = value
        value = formatting_command.sub(r"\1", value)
    value = re.sub(r"\\([%&_#$])", r"\1", value)
    return _normalize(value.replace("~", " "))


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
