from __future__ import annotations

import re
from uuid import uuid4

from ..types import CaptionLine, TranscriptWord

HARD_BREAK_PUNCTUATION = (".", "!", "?", "\u2026")
SOFT_BREAK_PUNCTUATION = (",", ";", ":")
TOKEN_EDGE_RE = re.compile(r"^\W+|\W+$", re.UNICODE)


def _compact_word(word: TranscriptWord) -> str:
    return " ".join(word.text.split())


def _word_core(value: str) -> str:
    return TOKEN_EDGE_RE.sub("", value).lower()


def _caption_text(words: list[TranscriptWord]) -> str:
    caption_text = " ".join(_compact_word(word) for word in words if _compact_word(word))
    return " ".join(caption_text.split())


def _caption_char_count(words: list[TranscriptWord]) -> int:
    return len(_caption_text(words))


def _ends_with_punctuation(value: str, punctuation: tuple[str, ...]) -> bool:
    return value.rstrip().endswith(punctuation)


def _boundary_score(
    left_words: list[TranscriptWord],
    right_words: list[TranscriptWord],
    *,
    max_chars: int,
) -> float:
    left_text = _caption_text(left_words)
    right_text = _caption_text(right_words)
    if not left_text or not right_text:
        return float("-inf")

    previous_word = _compact_word(left_words[-1])
    next_word = _compact_word(right_words[0])
    previous_core = _word_core(previous_word)
    next_core = _word_core(next_word)
    gap = max(0.0, right_words[0].start - left_words[-1].end)

    score = 0.0
    if _ends_with_punctuation(previous_word, HARD_BREAK_PUNCTUATION):
        score += 6.0
    elif _ends_with_punctuation(previous_word, SOFT_BREAK_PUNCTUATION):
        score += 3.0

    if gap >= 0.55:
        score += 4.5
    elif gap >= 0.35:
        score += 2.8
    elif gap >= 0.22:
        score += 1.3

    # Avoid leaving tiny bridge words dangling at the end of the previous subtitle.
    if previous_core and len(previous_core) <= 3 and not _ends_with_punctuation(
        previous_word,
        HARD_BREAK_PUNCTUATION + SOFT_BREAK_PUNCTUATION,
    ):
        score -= 4.0
    if next_core and len(next_core) <= 2:
        score -= 1.0

    left_chars = len(left_text)
    right_chars = len(right_text)
    total_chars = max(1, left_chars + right_chars)
    score -= abs(left_chars - right_chars) / total_chars

    if left_chars > max_chars:
        score -= 100.0
    if len(left_words) == 1 and len(left_text) <= 4:
        score -= 2.0
    if len(right_words) == 1 and len(right_text) <= 4:
        score -= 1.5

    return score


def _best_split_index(words: list[TranscriptWord], *, max_chars: int) -> int | None:
    if len(words) < 2:
        return None

    best_score = float("-inf")
    best_index: int | None = None
    for index in range(1, len(words)):
        left_words = words[:index]
        if _caption_char_count(left_words) > max_chars:
            continue
        score = _boundary_score(left_words, words[index:], max_chars=max_chars)
        if score > best_score:
            best_score = score
            best_index = index

    return best_index


def _should_flush_before_word(
    active_words: list[TranscriptWord],
    next_word: TranscriptWord,
    *,
    active_char_count: int,
    max_chars: int,
    max_gap_seconds: float,
) -> bool:
    if not active_words:
        return False

    previous_word = _compact_word(active_words[-1])
    gap = max(0.0, next_word.start - active_words[-1].end)
    if gap >= max_gap_seconds:
        return True
    if _ends_with_punctuation(previous_word, HARD_BREAK_PUNCTUATION) and gap >= 0.08:
        return True
    if _ends_with_punctuation(previous_word, SOFT_BREAK_PUNCTUATION) and gap >= 0.2:
        return True
    if gap >= max_gap_seconds * 0.65 and active_char_count >= max(14, int(max_chars * 0.45)):
        return True
    return False


def _caption_time_bounds(chunks: list[list[TranscriptWord]]) -> list[tuple[float, float]]:
    if not chunks:
        return []

    raw_starts = [chunk[0].start for chunk in chunks]
    raw_ends = [chunk[-1].end for chunk in chunks]
    starts = raw_starts[:]
    ends = raw_ends[:]

    starts[0] = round(max(0.0, raw_starts[0] - min(0.08, raw_starts[0] * 0.5)), 3)
    ends[-1] = round(raw_ends[-1] + 0.08, 3)

    for index in range(len(chunks) - 1):
        gap = raw_starts[index + 1] - raw_ends[index]
        if gap <= 0:
            boundary = round((raw_ends[index] + raw_starts[index + 1]) / 2, 3)
            ends[index] = boundary
            starts[index + 1] = boundary
            continue

        ends[index] = round(raw_ends[index] + min(0.16, gap * 0.34), 3)
        starts[index + 1] = round(
            max(0.0, raw_starts[index + 1] - min(0.08, gap * 0.18)),
            3,
        )

        if ends[index] > starts[index + 1]:
            boundary = round((raw_ends[index] + raw_starts[index + 1]) / 2, 3)
            ends[index] = boundary
            starts[index + 1] = boundary

    return list(zip(starts, ends))


def build_caption_lines(
    words: list[TranscriptWord],
    *,
    max_chars: int = 32,
    max_gap_seconds: float = 0.52,
    max_duration_seconds: float = 4.6,
    max_words: int = 8,
) -> list[CaptionLine]:
    if not words:
        return []

    chunks: list[list[TranscriptWord]] = []
    active_words: list[TranscriptWord] = []
    active_char_count = 0

    def flush(words_to_flush: list[TranscriptWord] | None = None) -> None:
        nonlocal active_words, active_char_count
        chunk = words_to_flush if words_to_flush is not None else active_words
        if not chunk:
            return
        if _caption_text(chunk):
            chunks.append(chunk)
        if words_to_flush is None:
            active_words = []
            active_char_count = 0

    for word in words:
        cleaned = _compact_word(word)
        if not cleaned:
            continue

        if not active_words:
            active_words = [word]
            active_char_count = len(cleaned)
            continue

        if _should_flush_before_word(
            active_words,
            word,
            active_char_count=active_char_count,
            max_chars=max_chars,
            max_gap_seconds=max_gap_seconds,
        ):
            flush()
            active_words = [word]
            active_char_count = len(cleaned)
            continue

        projected_words = active_words + [word]
        projected_duration = projected_words[-1].end - projected_words[0].start
        projected_chars = _caption_char_count(projected_words)
        if (
            projected_duration > max_duration_seconds
            or projected_chars > max_chars
            or len(projected_words) > max_words
        ):
            split_index = _best_split_index(projected_words, max_chars=max_chars)
            if split_index is None or split_index >= len(projected_words):
                flush()
                active_words = [word]
            else:
                flush(projected_words[:split_index])
                active_words = projected_words[split_index:]
            active_char_count = _caption_char_count(active_words)
            continue

        active_words = projected_words
        active_char_count = projected_chars

    flush()

    timings = _caption_time_bounds(chunks)
    captions: list[CaptionLine] = []
    for chunk, (start, end) in zip(chunks, timings):
        caption_text = _caption_text(chunk)
        if not caption_text:
            continue
        captions.append(
            CaptionLine(
                id=uuid4().hex,
                text=caption_text,
                start=start,
                end=end,
            )
        )

    return captions
