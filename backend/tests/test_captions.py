from backend.app.services.captions import build_caption_lines
from backend.app.types import TranscriptWord


def test_build_caption_lines_splits_on_gap_and_length():
    words = [
        TranscriptWord(id="1", text="Hello", start=0.0, end=0.4),
        TranscriptWord(id="2", text="from", start=0.41, end=0.6),
        TranscriptWord(id="3", text="the", start=0.61, end=0.7),
        TranscriptWord(id="4", text="other", start=1.4, end=1.8),
        TranscriptWord(id="5", text="side", start=1.81, end=2.0),
    ]

    captions = build_caption_lines(words, max_chars=18, max_gap_seconds=0.45)

    assert len(captions) == 2
    assert captions[0].text == "Hello from the"
    assert captions[1].text == "other side"


def test_build_caption_lines_avoids_dangling_short_bridge_word():
    words = [
        TranscriptWord(id="1", text="write", start=0.0, end=0.2),
        TranscriptWord(id="2", text="track", start=0.21, end=0.45),
        TranscriptWord(id="3", text="for", start=0.46, end=0.58),
        TranscriptWord(id="4", text="me", start=0.59, end=0.7),
        TranscriptWord(id="5", text="tonight", start=0.71, end=1.02),
    ]

    captions = build_caption_lines(words, max_chars=15, max_gap_seconds=0.45)

    assert len(captions) == 2
    assert captions[0].text == "write track"
    assert captions[1].text == "for me tonight"


def test_build_caption_lines_adds_small_timing_padding_without_overlap():
    words = [
        TranscriptWord(id="1", text="hello", start=1.0, end=1.16),
        TranscriptWord(id="2", text="again", start=1.9, end=2.14),
    ]

    captions = build_caption_lines(words, max_gap_seconds=0.5)

    assert len(captions) == 2
    assert captions[0].start < 1.0
    assert captions[0].end > 1.16
    assert captions[1].start < 1.9
    assert captions[0].end <= captions[1].start
