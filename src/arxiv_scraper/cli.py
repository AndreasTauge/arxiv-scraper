from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .client import DEFAULT_CATEGORIES, ArxivClient, ArxivError
from .models import Paper
from .notifications import (
    DiscordNotifier,
    EmailNotifier,
    EmailSettings,
    NotificationError,
    Notifier,
)
from .state import DeliveryState, default_state_path
from .summarizer import ExtractiveSummarizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arxiv-scraper",
        description="Find and summarize recent machine-learning papers on arXiv.",
    )
    parser.add_argument(
        "query", nargs="?", help="keywords to search for, such as 'diffusion model'"
    )
    parser.add_argument(
        "-c",
        "--category",
        action="append",
        dest="categories",
        metavar="ID",
        help="arXiv category to include; repeat this option (default: common ML categories)",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=positive_int,
        default=7,
        help="look back N days (default: 7)",
    )
    parser.add_argument(
        "-n",
        "--max-results",
        type=result_count,
        default=10,
        help="return at most N papers (1-100)",
    )
    parser.add_argument(
        "--sort",
        choices=("auto", "relevance", "submitted", "updated"),
        default="auto",
        help="result ordering (default: relevance with keywords, otherwise newest)",
    )
    parser.add_argument("--summary-sentences", type=positive_int, default=2)
    parser.add_argument(
        "--no-summary", action="store_true", help="show the original abstract instead"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    delivery = parser.add_argument_group("daily delivery")
    delivery.add_argument("--email-to", metavar="ADDRESS", help="email new papers to this address")
    delivery.add_argument(
        "--discord", action="store_true", help="send new papers to a Discord webhook"
    )
    delivery.add_argument(
        "--state-file",
        type=Path,
        default=default_state_path(),
        help="delivery history used to prevent duplicates",
    )
    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


# prevent a stupid amount of papers returned
def result_count(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 100:
        raise argparse.ArgumentTypeError("must be no greater than 100")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    categories = tuple(args.categories) if args.categories else DEFAULT_CATEGORIES
    sort_map = {
        "auto": None,
        "relevance": "relevance",
        "submitted": "submittedDate",
        "updated": "lastUpdatedDate",
    }

    try:
        papers = ArxivClient().search(
            args.query,
            categories=categories,
            days=args.days,
            max_results=args.max_results,
            sort_by=sort_map[args.sort],
        )
    except (ArxivError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summarizer = ExtractiveSummarizer(args.summary_sentences)
    summaries = [
        paper.abstract if args.no_summary else summarizer.summarize(paper.abstract)
        for paper in papers
    ]

    if args.json:
        output = [paper.to_dict(summary=summary) for paper, summary in zip(papers, summaries)]
        print(json.dumps(output, indent=2))
    else:
        _print_papers(papers, summaries)

    try:
        notifiers = []
        if args.email_to:
            notifiers.append(EmailNotifier(EmailSettings.from_environment(args.email_to)))
        if args.discord:
            notifiers.append(DiscordNotifier.from_environment())
        return _deliver_new(notifiers, papers, summaries, args.state_file)
    except (NotificationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _print_papers(papers: Sequence[Paper], summaries: Sequence[str]) -> None:
    if not papers:
        print("No matching papers found.")
        return
    for index, (paper, summary) in enumerate(zip(papers, summaries), start=1):
        print(f"{index}. {paper.title}")
        print(f"   {', '.join(paper.authors)}")
        category = paper.primary_category or "uncategorized"
        print(f"   {paper.published.date()} · {category} · {paper.url}")
        print(f"   {summary}\n")


def _deliver_new(
    notifiers: list[Notifier],
    papers: list[Paper],
    summaries: list[str],
    state_path: Path,
) -> int:
    if not notifiers:
        return 0
    state = DeliveryState(state_path)
    failed = False
    paper_ids = [paper.arxiv_id for paper in papers]
    for notifier in notifiers:
        mask = state.unseen(notifier.channel_id, paper_ids)
        new_papers = [paper for paper, unseen in zip(papers, mask) if unseen]
        new_summaries = [summary for summary, unseen in zip(summaries, mask) if unseen]
        if not new_papers:
            print(f"No new papers to deliver to {notifier.channel_id}.", file=sys.stderr)
            continue
        try:
            notifier.send(new_papers, new_summaries)
            state.mark_delivered(notifier.channel_id, [paper.arxiv_id for paper in new_papers])
            print(
                f"Delivered {len(new_papers)} paper(s) to {notifier.channel_id}.",
                file=sys.stderr,
            )
        except (NotificationError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
