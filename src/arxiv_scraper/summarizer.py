from __future__ import annotations

import math
import re
from collections import Counter

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WORDS = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
_RESULT_CUES = {
    "achieve",
    "achieves",
    "improve",
    "improves",
    "outperform",
    "outperforms",
    "result",
    "results",
    "show",
    "shows",
    "state-of-the-art",
    "surpass",
    "surpasses",
}
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "among",
    "and",
    "are",
    "been",
    "being",
    "between",
    "both",
    "but",
    "can",
    "could",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "into",
    "its",
    "may",
    "more",
    "most",
    "not",
    "our",
    "over",
    "such",
    "than",
    "that",
    "the",
    "their",
    "these",
    "they",
    "this",
    "those",
    "through",
    "using",
    "was",
    "were",
    "which",
    "while",
    "will",
    "with",
    "would",
    "your",
}


class ExtractiveSummarizer:
    """Select representative sentences without a model or network request."""

    def __init__(self, sentence_count: int = 2) -> None:
        if sentence_count < 1:
            raise ValueError("sentence_count must be positive")
        self.sentence_count = sentence_count

    def summarize(self, text: str) -> str:
        clean_text = " ".join(text.split())
        if not clean_text:
            return ""
        sentences = _SENTENCE_BOUNDARY.split(clean_text)
        if len(sentences) <= self.sentence_count:
            return clean_text

        tokenized = [self._meaningful_words(sentence) for sentence in sentences]
        frequencies = Counter(word for words in tokenized for word in set(words))
        scores: list[tuple[float, int]] = []
        for index, words in enumerate(tokenized):
            if not words:
                score = 0.0
            else:
                # Reward salient terms but keep very long sentences from dominating.
                score = sum(math.log1p(frequencies[word]) for word in words) / math.sqrt(len(words))
                if _RESULT_CUES.intersection(words):
                    score *= 1.25
            if index == 0:
                score *= 1.15
            scores.append((score, index))

        selected = sorted(index for _, index in sorted(scores, reverse=True)[: self.sentence_count])
        return " ".join(sentences[index] for index in selected)

    @staticmethod
    def _meaningful_words(text: str) -> list[str]:
        return [
            word
            for match in _WORDS.finditer(text)
            if (word := match.group().lower()) not in _STOP_WORDS
        ]
