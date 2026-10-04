from swarm.training_pool import contamination, derive_false_premises, frame_title_overlap, normalize_2wiki, normalize_musique, stratified_split, word_jaccard


def test_normalizers_keep_source_evidence_offline():
    musique = normalize_musique([{"id": "m1", "question": "When?", "answer": "1900",
        "question_decomposition": [{"question": "When was it founded?"}],
        "paragraphs": [{"title": "Thing", "paragraph_text": "Thing was founded in 1900.", "is_supporting": True}]}])
    two = normalize_2wiki([{"id": "w1", "question": "Who?", "answer": "Ada", "type": "bridge_comparison",
        "supporting_facts": {"title": ["Thing"], "sent_id": [0]},
        "context": {"title": ["Thing"], "sentences": [["Thing was created by Ada."]]}}])
    assert musique[0]["type"] == "compositional" and musique[0]["_docs"][0]["text"]
    assert musique[0]["_docs"][0]["source"] == "web" and musique[0]["_docs"][0]["url"].startswith("https://en.wikipedia.org/wiki/")
    assert two[0]["type"] == "bridge-comparison" and two[0]["supporting_titles"] == ["Thing"]


def test_false_premise_only_uses_explicit_year():
    item = {"id": "x", "question": "Q", "answer": "A", "source": "x", "type": "2hop", "answerable": True,
            "supporting_titles": ["Thing"], "_docs": [{"title": "Thing", "text": "Thing was founded in 1900.", "source": "web", "url": "https://en.wikipedia.org/wiki/Thing", "error": ""}]}
    out = derive_false_premises([item], 1, 4)
    assert len(out) == 1 and out[0]["answerable"] is False and "1900" in out[0]["answer"]
    shifted = int(out[0]["question"].rsplit(" ", 1)[-1].rstrip("?"))
    assert 3 <= shifted - 1900 <= 15 and out[0]["question"].startswith("Why was Thing founded")


def test_unanswerable_rows_use_their_own_flag_and_reference_answer():
    rows = [{"id": "u", "question": "What?", "answer": "", "answerable": False,
             "paragraphs": [{"title": "Thing", "paragraph_text": "A partial fact.", "is_supporting": True}]}]
    out = normalize_musique(rows, None)
    assert out[0]["type"] == "unanswerable" and out[0]["answerable"] is False
    assert out[0]["answer"].startswith("The evidence does not contain")


def test_duplicate_question_normalization_is_stable():
    assert word_jaccard("Who founded Thing?", "Who founded Thing!") == 1.0


def test_contamination_and_frame_rule():
    assert word_jaccard("A blue bird flew", "A blue bird flew away") > 0.6
    assert contamination("An event in 2026", [], []) == "events_2026"
    assert contamination("Same question", ["Same question"], []) == "eval_exact"
    assert frame_title_overlap(["A", "B"], [{"a", "b"}])


def test_stratified_split_is_deterministic():
    rows = [{"id": str(i), "source": "s" + str(i % 2), "type": "t" + str(i % 3)} for i in range(30)]
    a, b = stratified_split(rows, 7)
    c, d = stratified_split(rows, 7)
    assert (a, b) == (c, d) and len(a) + len(b) == 30
