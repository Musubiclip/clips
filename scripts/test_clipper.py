from clipper import caption_chunks, crop_expression, crop_x, tidy_clips


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


def test_crop_expression_switches_per_shot():
    assert crop_expression([(0, 10)]) == "10"
    assert crop_expression([(0, 10), (2.5, 40), (6, 70)]) == "if(lt(t,2.500),10,if(lt(t,6.000),40,70))"


def test_crop_x_clamps_to_frame():
    assert crop_x(None, 1920, 608) == 656
    assert crop_x(0, 1920, 608) == 0
    assert crop_x(1900, 1920, 608) == 1312


def test_captions_break_on_size_gap_and_punctuation():
    words = [word("a", 0, 0.2), word("b", 0.2, 0.4), word("c.", 0.4, 0.6), word("d", 0.6, 0.8),
             word("e", 2.0, 2.2), word("f", 2.2, 2.4), word("g", 2.4, 2.6), word("h", 2.6, 2.8)]
    assert [[w["word"] for w in c] for c in caption_chunks(words)] == [["a", "b", "c."], ["d"], ["e", "f", "g"], ["h"]]


def test_tidy_snaps_drops_overlaps_and_ranks():
    words = [word(str(i), i, i + 0.9) for i in range(200)]
    scores = {"hook": 3, "standalone": 3, "payoff": 3, "emotion": 3}
    raw = [
        {**scores, "start": 10.2, "end": 40.3, "title": "a", "cold_open_start": 30.1, "cold_open_end": 33.4},
        {**scores, "start": 20, "end": 50, "title": "overlaps a"},
        {**scores, "start": 100, "end": 105, "title": "too short"},
        {**scores, "hook": 5, "start": 60, "end": 90, "title": "best", "cold_open_start": 60, "cold_open_end": 63},
    ]
    clips = tidy_clips(raw, words, 5)
    assert [c["title"] for c in clips] == ["best", "a"]
    assert (clips[1]["start"], clips[1]["end"], clips[1]["cold_open"]) == (10, 39.9, [30, 32.9])
    assert clips[0]["cold_open"] is None


def test_captions_never_overlap():
    from clipper import build_ass
    words = [word("one", 0, 0.3), word("two", 0.3, 0.6), word("three.", 0.6, 1.0), word("four", 1.05, 1.4), word("five", 3.0, 3.3)]
    clip = {"start": 0, "end": 4, "cold_open": None, "hook_text": "hi"}
    lines = [l.split(",") for l in build_ass(clip, words).splitlines() if l.startswith("Dialogue: 0")]
    spans = [(l[1], l[2]) for l in lines]
    assert spans == [("0:00:00.00", "0:00:00.30"), ("0:00:00.30", "0:00:00.60"), ("0:00:00.60", "0:00:01.05"),
                     ("0:00:01.05", "0:00:01.55"), ("0:00:03.00", "0:00:03.30")]


def test_split_words_rejoin():
    from clipper import build_ass
    words = [word("all", 0, 0.3), word("-nighters", 0.3, 0.6)]
    ass = build_ass({"start": 0, "end": 1, "cold_open": None, "hook_text": "hi"}, words)
    assert "all{\\c&H0000E5FF&}-nighters" in ass


def test_youtube_words_and_segments(tmp_path):
    import json
    from clipper import group_segments, youtube_words
    caption = tmp_path / "c.json3"
    caption.write_text(json.dumps({"events": [
        {"tStartMs": 1000, "segs": [{"utf8": ">> so"}, {"utf8": " [music]", "tOffsetMs": 100}, {"utf8": " [sound", "tOffsetMs": 120}, {"utf8": " of", "tOffsetMs": 140}, {"utf8": " throat]", "tOffsetMs": 160}, {"utf8": " in", "tOffsetMs": 200}]},
        {"tStartMs": 1500, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 4000, "segs": [{"utf8": "college"}, {"utf8": ".", "tOffsetMs": 300}]},
    ]}))
    words = youtube_words(caption)
    assert words == [{"word": "so", "start": 1.0, "end": 1.2}, {"word": "in", "start": 1.2, "end": 2.0},
                     {"word": "college.", "start": 4.0, "end": 4.5}]
    assert [s["text"] for s in group_segments(words)] == ["so in", "college."]


def test_moment_problems_names_each_bad_field():
    from clipper import moment_problems
    good = {"start": 1, "end": 30, "title": "t", "hook_text": "h", "reason": "r", "hook": 3, "standalone": 3, "payoff": 3, "emotion": 3}
    assert moment_problems([good]) == []
    bad = {**good, "end": "30", "hook": 7, "title": ""}
    assert moment_problems([good, bad]) == ["moment 2: end must be a number of seconds", "moment 2: title is missing",
                                            "moment 2: hook must be a whole number from 1 to 5"]


def test_shifted_moves_clip_words_and_pieces_together():
    from clipper import clip_timeline, shifted
    words = [word("a", 100.0, 100.5), word("b", 101.0, 101.4)]
    clip = {"start": 100.0, "end": 102.0, "cold_open": [101.0, 101.4]}
    moved, moved_words = shifted(clip, words, 99.0)
    assert (moved["start"], moved["end"], [round(t, 6) for t in moved["cold_open"]]) == (1.0, 3.0, [2.0, 2.4])

    def rounded(timeline):
        return [(w["word"], round(w["start"], 6), round(w["end"], 6)) for w in timeline]

    assert rounded(clip_timeline(moved, moved_words)) == rounded(clip_timeline(clip, words))
