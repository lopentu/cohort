"""The three read-only evidence tools, and how a worker acquires them.

A toy corpus with two translators and a planted quotation: unit T0031 (grey)
reproduces a 24-character run of T0001 verbatim, with punctuation and a line
break inside it, so the alignment has to see through editorial characters and
report offsets into the *original* text. The embeddings are a tiny synthetic
index, because the tool's contract is about what it returns and excludes (its
own work), not about any encoder.
"""

from __future__ import annotations

import json
import random

import pytest

from cohort import attribution as attr
from cohort.agents.attestation_worker import (
    ALIGN_PASSAGES_NAME,
    ATTRIBUTION_EVIDENCE_NAME,
    SEMANTIC_NEIGHBORS_NAME,
    AttestationWorker,
)
from cohort.agents.review_worker import ReviewWorker
from cohort.errors import UnitNotInCorpus
from cohort.graph import Graph
from cohort.sources.local_reader import LocalReader
from cohort.tools.align_passages import AlignPassagesInput, align_passages
from cohort.tools.attribution_evidence import AttributionEvidenceInput, attribution_evidence
from cohort.tools.semantic_neighbors import SemanticNeighborsInput, semantic_neighbors

np = pytest.importorskip("numpy")

VOCAB_A = [chr(c) for c in range(0x4E00, 0x4E00 + 60)]
VOCAB_B = [chr(c) for c in range(0x5000, 0x5000 + 60)]
ZIPF = [1 / (i + 1) for i in range(60)]
QUOTE = "".join(VOCAB_A[i % 60] for i in range(0, 48, 2))  # 24 distinct-ish characters


def _text(rng, vocab, n=2400):
    return "".join(rng.choices(vocab, weights=ZIPF)[0] for _ in range(n))


@pytest.fixture
def corpus(tmp_path):
    rng = random.Random(3)
    units = {
        "T0001": ("A", _text(rng, VOCAB_A)), "T0002": ("A", _text(rng, VOCAB_A)),
        "T0003": ("A", _text(rng, VOCAB_A)), "T0004": ("A", _text(rng, VOCAB_A)),
        "T0005": ("A", _text(rng, VOCAB_A)),
        "T0011": ("B", _text(rng, VOCAB_B)), "T0012": ("B", _text(rng, VOCAB_B)),
        "T0013": ("B", _text(rng, VOCAB_B)), "T0014": ("B", _text(rng, VOCAB_B)),
        "T0015": ("B", _text(rng, VOCAB_B)),
        "T0099": ("grey", _text(rng, VOCAB_A)), "T0098": ("grey", _text(rng, VOCAB_B)),
    }
    # T0001 carries the quotation once, cleanly; T0031 (grey) reproduces it with
    # editorial punctuation and a line break in the middle.
    a = units["T0001"][1]
    units["T0001"] = ("A", a[:1000] + QUOTE + a[1000:])
    half = len(QUOTE) // 2
    units["T0031"] = ("grey", _text(rng, VOCAB_B, 800) + QUOTE[:half] + "，\n" + QUOTE[half:] + "。" + _text(rng, VOCAB_B, 800))
    corpus = tmp_path / attr.CORPUS_DIR
    for uid, (_, text) in units.items():
        (corpus / uid).mkdir(parents=True)
        (corpus / uid / "大.txt").write_text(text, encoding="utf-8")
    blocks = {}
    for uid, (label, _) in units.items():
        blocks.setdefault(label, []).append(uid)
    cat = "\r\n\r\n".join("\r\n".join(f"{u} {lab}" for u in us) for lab, us in blocks.items())
    (tmp_path / attr.CATALOGUE).write_bytes((cat + "\r\n").encode())
    grams = sorted({x + y for x in VOCAB_A for y in VOCAB_A})[:1100]
    (tmp_path / attr.MARKERS).write_text(
        "<t>" + "".join(f"<ngram>{g}</ngram>" for g in grams) + "</t>", encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def index(corpus):
    return attr.AttributionIndex.load(corpus, use_cache=False)


@pytest.fixture
def embeddings(corpus, tmp_path):
    """Two windows per unit for three units; T0031's windows are made to point
    at T0001's, and T0001's second window at itself (same work, must be excluded)."""
    from cohort.embeddings import EmbeddingIndex

    rng = np.random.default_rng(0)
    rows = [("T0001", "A", 0), ("T0001", "A", 400), ("T0031", "grey", 0), ("T0031", "grey", 400),
            ("T0011", "B", 0), ("T0011", "B", 400)]
    vec = rng.normal(size=(6, 8)).astype(np.float32)
    vec[2] = vec[0] + 0.01          # T0031 window 0 ≈ T0001 window 0
    vec[3] = vec[1] + 0.01          # T0031 window 1 ≈ T0001 window 1
    vec /= np.linalg.norm(vec, axis=1, keepdims=True)
    path = tmp_path / "emb.npz"
    np.savez(path, vec=vec.astype(np.float16), uid=np.array([r[0] for r in rows]),
             label=np.array([r[1] for r in rows]), start=np.array([r[2] for r in rows], dtype=np.int32))
    return EmbeddingIndex(path)


def test_attribution_evidence_is_a_compact_read(index):
    out = attribution_evidence(index, AttributionEvidenceInput(uid="T0099", features="generic"))
    assert out["verdict"] == "leans"
    assert out["first"] == "A"
    assert "excerpt" not in out
    assert "strip" not in out
    assert len(out["for"]) <= 8
    assert out["for"][0]["count_a"] > 0 or out["for"][0]["count_b"] > 0
    assert out["provenance"]["base_text"]["file"].endswith("T0099/大.txt")
    withheld = attribution_evidence(
        index, AttributionEvidenceInput(uid="T0099", features="generic", withhold=["T0002", "T0003"]),
    )
    assert withheld["profiles"]["A"]["units"] == out["profiles"]["A"]["units"] - 2


def test_align_passages_sees_through_punctuation_and_cites_original_offsets(index):
    out = align_passages(index, AlignPassagesInput(uid_a="T0031", uid_b="T0001", min_run=12))
    assert out["longest_shared_run"] >= len(QUOTE)
    run = out["runs"][0]
    assert QUOTE in run["text"]
    a_text = index.base_text(index.root, "T0031")
    b_text = index.base_text(index.root, "T0001")
    # The offsets point into the original texts, punctuation included.
    assert a_text[run["a_offset"]] == run["text"][0]
    assert b_text[run["b_offset"] : run["b_offset"] + len(run["text"])] == run["text"]
    assert out["share_of_a_in_b"] > 0
    unrelated = align_passages(index, AlignPassagesInput(uid_a="T0011", uid_b="T0001"))
    assert unrelated["share_of_a_in_b"] == 0.0
    assert unrelated["longest_shared_run"] < 12


def test_semantic_neighbors_excludes_the_unit_s_own_work(index, embeddings):
    out = semantic_neighbors(embeddings, index, SemanticNeighborsInput(uid="T0031", top_k=2))
    assert out["windows"] == 2
    assert out["nearest_unit_tally"][0][0] == "T0001"
    for w in out["shown"]:
        assert all(n["uid"] != "T0031" for n in w["neighbors"])
        assert w["neighbors"][0]["uid"] == "T0001"
        assert isinstance(w["excerpt"], str)
        assert isinstance(w["neighbors"][0]["excerpt"], str)
    own = semantic_neighbors(embeddings, index, SemanticNeighborsInput(uid="T0001", top_k=1))
    assert all(n["uid"] != "T0001" for w in own["shown"] for n in w["neighbors"])
    with pytest.raises(UnitNotInCorpus):
        semantic_neighbors(embeddings, index, SemanticNeighborsInput(uid="T0099"))


def _fake_transport(calls: list[dict]):
    """Answers the first turn with the given tool calls, then stops."""
    turns = {"n": 0}

    def transport(url, headers, body, timeout):
        turns["n"] += 1
        if turns["n"] == 1:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                for i, c in enumerate(calls)
            ]}
            fin = "tool_calls"
        else:
            msg, fin = {"role": "assistant", "content": "done"}, "stop"
        return 200, json.dumps({"id": "x", "model": "m", "choices": [{"message": msg, "finish_reason": fin}],
                                "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
    return transport


def test_a_worker_registers_the_evidence_tools_only_with_their_data(tmp_path, index, embeddings):
    source = LocalReader(__import__("pathlib").Path(__file__).parent.parent / "examples" / "local_corpus")
    graph = Graph.open(tmp_path / "g.sqlite", tmp_path / "g.jsonl")
    try:
        plain = AttestationWorker(graph, source, authored_by="agent:w", model="m", api_key="k")
        assert {t["function"]["name"] for t in plain.tools}.isdisjoint(
            {ATTRIBUTION_EVIDENCE_NAME, ALIGN_PASSAGES_NAME, SEMANTIC_NEIGHBORS_NAME})
        assert "evidence tools" not in plain.system_prompt
        no_emb = AttestationWorker(graph, source, authored_by="agent:w", model="m", api_key="k", attribution=index)
        names = {t["function"]["name"] for t in no_emb.tools}
        assert {ATTRIBUTION_EVIDENCE_NAME, ALIGN_PASSAGES_NAME} <= names
        assert SEMANTIC_NEIGHBORS_NAME not in names
        assert "evidence tools" in no_emb.system_prompt
        full = AttestationWorker(graph, source, authored_by="agent:w", model="m", api_key="k",
                                 attribution=index, embeddings=embeddings)
        assert SEMANTIC_NEIGHBORS_NAME in {t["function"]["name"] for t in full.tools}
        reviewer = ReviewWorker(graph, source, authored_by="agent:r", model="m", api_key="k",
                                attribution=index, embeddings=embeddings)
        assert {t["function"]["name"] for t in reviewer.tools}.isdisjoint({ATTRIBUTION_EVIDENCE_NAME})
    finally:
        source.close()
        graph.close()


def test_a_worker_dispatches_the_chain_and_reads_never_write(tmp_path, index, embeddings):
    source = LocalReader(__import__("pathlib").Path(__file__).parent.parent / "examples" / "local_corpus")
    graph = Graph.open(tmp_path / "g.sqlite", tmp_path / "g.jsonl")
    try:
        worker = AttestationWorker(
            graph, source, authored_by="agent:w", model="m", api_key="k", attribution=index,
            embeddings=embeddings, transport=_fake_transport([
                {"name": ATTRIBUTION_EVIDENCE_NAME, "args": {"uid": "T0031", "features": "generic"}},
                {"name": SEMANTIC_NEIGHBORS_NAME, "args": {"uid": "T0031", "top_k": 1}},
                {"name": ALIGN_PASSAGES_NAME, "args": {"uid_a": "T0031", "uid_b": "T0001"}},
                {"name": ATTRIBUTION_EVIDENCE_NAME, "args": {"uid": "T0031", "features": "generic", "withhold": ["T0001"]}},
                {"name": ALIGN_PASSAGES_NAME, "args": {"uid_a": "T0031", "uid_b": "T9999"}},
            ]),
        )
        log = worker.run("chain", max_turns=3)
        assert [e["is_error"] for e in log] == [False, False, False, False, True]
        assert log[1]["result"]["nearest_unit_tally"][0][0] == "T0001"
        assert log[2]["result"]["longest_shared_run"] >= len(QUOTE)
        assert log[3]["result"]["withheld_extra"] == ["T0001"]
        assert "T9999" in log[4]["result"]
        # Nothing was written: the evidence tools are reads.
        counts = {r["type"]: r["c"] for r in graph.conn.execute("SELECT type, COUNT(*) c FROM nodes GROUP BY type")}
        assert counts == {}
    finally:
        source.close()
        graph.close()
