from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def default_state_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return root / "arxiv-scraper" / "delivered.json"


class DeliveryState:
    """Track delivered arXiv IDs separately for each destination."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._channels = self._load()

    def unseen(self, channel: str, paper_ids: list[str]) -> list[bool]:
        delivered = self._channels.get(channel, set())
        return [paper_id not in delivered for paper_id in paper_ids]

    def mark_delivered(self, channel: str, paper_ids: list[str]) -> None:
        self._channels.setdefault(channel, set()).update(paper_ids)
        self._save()

    def _load(self) -> dict[str, set[str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("state root is not an object")
            return {
                str(channel): {str(item) for item in paper_ids}
                for channel, paper_ids in data.items()
                if isinstance(paper_ids, list)
            }
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"could not read delivery state {self.path}: {exc}") from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {channel: sorted(ids) for channel, ids in sorted(self._channels.items())}
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as temporary:
                json.dump(payload, temporary, indent=2)
                temporary.write("\n")
                temporary_name = temporary.name
            os.replace(temporary_name, self.path)
        except OSError as exc:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
            raise ValueError(f"could not save delivery state {self.path}: {exc}") from exc
