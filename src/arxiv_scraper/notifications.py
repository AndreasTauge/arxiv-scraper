from __future__ import annotations

import hashlib
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from typing import Protocol
from dataclasses import dataclass
from email.message import EmailMessage

from .models import Paper


class NotificationError(RuntimeError):
    """Raised when a digest cannot be configured or delivered."""


class Notifier(Protocol):
    channel_id: str

    def send(self, papers: list[Paper], summaries: list[str]) -> None: ...


def format_digest(papers: list[Paper], summaries: list[str]) -> str:
    sections = [f"{len(papers)} new machine-learning paper{'s' if len(papers) != 1 else ''}\n"]
    for index, (paper, summary) in enumerate(zip(papers, summaries), start=1):
        sections.append(
            "\n".join(
                (
                    f"{index}. {paper.title}",
                    f"Authors: {', '.join(paper.authors)}",
                    f"Published: {paper.published.date()} · {paper.primary_category}",
                    f"Summary: {summary}",
                    f"Paper: {paper.url}",
                    f"PDF: {paper.pdf_url}" if paper.pdf_url else "",
                )
            ).rstrip()
        )
    return "\n\n".join(sections)


@dataclass(frozen=True, slots=True)
class EmailSettings:
    host: str
    port: int
    sender: str
    recipient: str
    username: str | None
    password: str | None
    security: str

    @classmethod
    def from_environment(cls, recipient: str) -> EmailSettings:
        host = os.environ.get("ARXIV_SMTP_HOST")
        sender = os.environ.get("ARXIV_EMAIL_FROM")
        if not host or not sender:
            raise NotificationError("email requires ARXIV_SMTP_HOST and ARXIV_EMAIL_FROM")
        security = os.environ.get("ARXIV_SMTP_SECURITY", "starttls").lower()
        if security not in {"starttls", "ssl", "none"}:
            raise NotificationError("ARXIV_SMTP_SECURITY must be starttls, ssl, or none")
        default_port = 465 if security == "ssl" else 587
        try:
            port = int(os.environ.get("ARXIV_SMTP_PORT", default_port))
        except ValueError as exc:
            raise NotificationError("ARXIV_SMTP_PORT must be an integer") from exc
        return cls(
            host=host,
            port=port,
            sender=sender,
            recipient=recipient,
            username=os.environ.get("ARXIV_SMTP_USERNAME"),
            password=os.environ.get("ARXIV_SMTP_PASSWORD"),
            security=security,
        )


class EmailNotifier:
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings
        self.channel_id = f"email:{settings.recipient.lower()}"

    def send(self, papers: list[Paper], summaries: list[str]) -> None:
        message = EmailMessage()
        plural = "s" if len(papers) != 1 else ""
        message["Subject"] = f"Paper digest: {len(papers)} new result{plural}"
        message["From"] = self.settings.sender
        message["To"] = self.settings.recipient
        message.set_content(format_digest(papers, summaries))
        context = ssl.create_default_context()
        try:
            if self.settings.security == "ssl":
                server = smtplib.SMTP_SSL(
                    self.settings.host, self.settings.port, timeout=30, context=context
                )
            else:
                server = smtplib.SMTP(self.settings.host, self.settings.port, timeout=30)
            with server:
                if self.settings.security == "starttls":
                    server.starttls(context=context)
                if self.settings.username:
                    server.login(self.settings.username, self.settings.password or "")
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotificationError(f"email delivery failed: {exc}") from exc


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        allowed_prefixes = (
            "https://discord.com/api/webhooks/",
            "https://discordapp.com/api/webhooks/",
        )
        if not webhook_url.startswith(allowed_prefixes):
            raise NotificationError("ARXIV_DISCORD_WEBHOOK_URL is not a Discord webhook URL")
        self.webhook_url = webhook_url
        fingerprint = hashlib.sha256(webhook_url.encode()).hexdigest()[:12]
        self.channel_id = f"discord:{fingerprint}"

    @classmethod
    def from_environment(cls) -> DiscordNotifier:
        webhook_url = os.environ.get("ARXIV_DISCORD_WEBHOOK_URL")
        if not webhook_url:
            raise NotificationError("Discord requires ARXIV_DISCORD_WEBHOOK_URL")
        return cls(webhook_url)

    def send(self, papers: list[Paper], summaries: list[str]) -> None:
        for content in _discord_messages(papers, summaries):
            request = urllib.request.Request(
                self.webhook_url,
                data=json.dumps({"content": content}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "arxiv-paper-scraper/0.1",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=30):
                    pass
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
            ) as exc:
                raise NotificationError(f"Discord delivery failed: {exc}") from exc


def _discord_messages(papers: list[Paper], summaries: list[str]) -> list[str]:
    messages = []
    for paper, summary in zip(papers, summaries):
        authors = ", ".join(paper.authors)
        content = (
            f"**{paper.title}**\n{authors}\n"
            f"{paper.published.date()} · `{paper.primary_category}`\n"
            f"{summary}\n<{paper.url}>"
        )
        # Discord messages have a 2,000-character limit.
        messages.append(content if len(content) <= 2000 else content[:1997] + "...")
    return messages
