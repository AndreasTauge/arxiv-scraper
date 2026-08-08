# arxiv-scraper

A small command-line tool and Python library for finding recent machine-learning papers on
arXiv and turning their abstracts into short, readable summaries.

The project queries arXiv's public Atom API. By default it
searches papers posted in the last seven days across `cs.LG`, `cs.AI`, `stat.ML`, `cs.CL`, and
`cs.CV`.

## Features

- Search by natural-language keywords and one or more arXiv categories
- Restrict results to a recent time window
- Sort by relevance, submission date, or update date
- Parse titles, authors, abstracts, categories, dates, and paper/PDF links
- Produce local extractive summaries based on the abstract 
- Print readable terminal output or JSON for use by other programs
- Deliver new-paper digests by email, Discord, or both without sending duplicates
- Use the scraper and summarizer independently as Python classes

## Requirements

- Python 3.10 or newer
- Internet access when querying arXiv

The application has no runtime dependencies outside the Python standard library.

## Installation

Clone the repository, create a virtual environment, and install it in editable mode:

```bash
git clone <repository-url>
cd arxiv-scraper
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

The `arxiv-scraper` command will then be available in the active environment.

## Usage

Show the newest papers from the default ML categories:

```bash
arxiv-scraper
```

Search the last 14 days for papers about diffusion models:

```bash
arxiv-scraper "diffusion models" --days 14
```

Search specific categories and return five papers:

```bash
arxiv-scraper "vision language models" \
  --category cs.CV \
  --category cs.CL \
  --max-results 5
```

Emit JSON for a script or pipeline:

```bash
arxiv-scraper "graph neural networks" --json
```

Show full abstracts instead of generated summaries:

```bash
arxiv-scraper "reinforcement learning" --no-summary
```

Run `arxiv-scraper --help` for every option. Keyword searches default to relevance ordering;
category-only searches default to newest first. Use `--sort` to override that behavior.

## Email and Discord digests

Delivery is optional. Secrets are read from environment variables. 

### Email configuration

Set the SMTP connection used by your email provider:

```bash
export ARXIV_SMTP_HOST="smtp.example.com"
export ARXIV_SMTP_PORT="587"
export ARXIV_SMTP_SECURITY="starttls"
export ARXIV_SMTP_USERNAME="your-username"
export ARXIV_SMTP_PASSWORD="your-app-password"
export ARXIV_EMAIL_FROM="papers@example.com"
```

`ARXIV_SMTP_SECURITY` accepts `starttls` (the default), `ssl`, or `none`. The username and
password are optional for SMTP servers that do not require authentication.

Send new results by email:

```bash
arxiv-scraper "efficient language models" --days 1 --email-to you@example.com
```

### Discord configuration

Create a webhook in the target Discord channel's **Integrations → Webhooks** settings, then set:

```bash
export ARXIV_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Send new results to Discord:

```bash
arxiv-scraper "efficient language models" --days 1 --discord
```

Use both flags to deliver the same search to both destinations:

```bash
arxiv-scraper "efficient language models" \
  --days 1 \
  --max-results 10 \
  --email-to you@example.com \
  --discord
```

Delivered arXiv IDs are stored in
`~/.local/state/arxiv-scraper/delivered.json`. A successful email is recorded even if Discord
fails, and vice versa. Override the location with `--state-file`. Delete that file only if you
intentionally want previously delivered papers to be sent again.

### Run it every day

Put the environment variables above in a private file such as `~/.config/arxiv-scraper.env` and
restrict access to it:

```bash
chmod 600 ~/.config/arxiv-scraper.env
```

Then edit your crontab with `crontab -e` and, for example, add a daily run at 08:00:

```cron
0 8 * * * . "$HOME/.config/arxiv-scraper.env"; "$HOME/dev/arxiv-scraper/.venv/bin/arxiv-scraper" "efficient language models" --days 2 --max-results 10 --email-to you@example.com --discord >> "$HOME/.local/state/arxiv-scraper/digest.log" 2>&1
```

## Python API

```python
from arxiv_scraper import ArxivClient, ExtractiveSummarizer

client = ArxivClient()
summarizer = ExtractiveSummarizer(sentence_count=2)

papers = client.search(
    "retrieval augmented generation",
    categories=("cs.CL", "cs.AI"),
    days=30,
    max_results=5,
)

for paper in papers:
    print(paper.title)
    print(summarizer.summarize(paper.abstract))
    print(paper.url)
```

`ArxivClient.search` raises `ArxivError` for network and response-format failures, and
`ValueError` for invalid arguments. The returned `Paper` objects are immutable dataclasses.

## How summaries work

The built-in summarizer is fairly simple. It splits an abstract into
sentences, scores them using recurring meaningful terms and result-oriented language, and
returns the best sentences in their original order. In the future it may be fun to add a model-based summarizer of the full paper.

This is an **extractive summary of the author-provided abstract**. It does not read the full
PDF, generate new claims, or provide a critical assessment of the research. 

## Project structure

```text
src/arxiv_scraper/
├── cli.py          # argument parsing and output formatting
├── client.py       # query construction, HTTP access, and Atom parsing
├── models.py       # immutable paper model
└── summarizer.py   # dependency-free extractive summarizer
tests/
├── test_cli.py
├── test_client.py
└── test_summarizer.py
```

## Development

Run the test suite without installing additional tools:

```bash
PYTHONPATH=src python3 -m unittest discover -v
```

Optional development tools can be run if installed:

```bash
ruff check .
ruff format --check .
```

Tests use a representative saved Atom response and do not contact arXiv.

## Data source and disclaimer

Thank you to arXiv for use of its open access interoperability.

## License

See [LICENSE](LICENSE).
