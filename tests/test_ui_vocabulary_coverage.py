"""Every member of the closed vocabulary must be drawable.

The vocabulary is closed and adding to it takes a recorded argument (§6), so
the frontend can enumerate it — but nothing made it. On 2026-09-02 `question`
and `addresses` were added to the vocabulary and to every server-side view,
and neither reached `graph-model.js`: `layout()` keeps only nodes whose type
appears in some column, so **question nodes were silently dropped from the
graph view** while showing correctly in Findings and the API, and `addresses`
fell through to `EDGE_STYLE.part_of` and drew as bookkeeping.

Silently is the problem. A node type nobody styled should look wrong, not look
absent — an evidence graph that omits part of the evidence without saying so is
the one failure mode this whole project is against. Same reasoning as
`test_parity.py`: the two front ends may differ in presentation, never in what
they admit exists.

Text assertions over the JS source, like `test_ui_theme.py`, because there is
no JS test runner here and adding one for three greps would be a build step the
project does not otherwise need.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from cohort.schemas import EdgeType, NodeType

SRC = Path(__file__).parent.parent / "cohort" / "ui" / "frontend" / "src"
MODEL_PATH = SRC / "graph-model.js"

pytestmark = pytest.mark.skipif(
    not MODEL_PATH.is_file(), reason="frontend sources not present"
)


@pytest.fixture(scope="module")
def model() -> str:
    return MODEL_PATH.read_text(encoding="utf-8")


def _block(src: str, name: str) -> str:
    """The literal assigned to `export const <name>`, up to its closing line."""
    m = re.search(rf"export const {name} = (\[|\{{)(.*?)^(\]|\}})", src, re.S | re.M)
    assert m, f"{name} not found in graph-model.js"
    return m.group(2)


def test_every_node_type_has_a_column(model):
    """`layout()` filters by column membership, so a type in no column is not
    merely unstyled — it is invisible, and the view reports a smaller graph
    than exists without a word about it."""
    columns = _block(model, "COLUMNS")
    missing = [t for t in NodeType if f"'{t.value}'" not in columns]
    assert not missing, (
        f"node types absent from COLUMNS and therefore dropped from the graph: "
        f"{[t.value for t in missing]}"
    )


def test_every_edge_type_has_its_own_style(model):
    """`EDGE_STYLE[e.type] || EDGE_STYLE.part_of` means an unstyled edge does
    not fail, it *lies* — it draws as structural bookkeeping. A new edge type
    was added because it meant something the existing ones did not."""
    styles = _block(model, "EDGE_STYLE")
    missing = [t for t in EdgeType if not re.search(rf"^\s*{t.value}\s*:", styles, re.M)]
    assert not missing, (
        f"edge types with no EDGE_STYLE entry, silently drawn as `part_of`: "
        f"{[t.value for t in missing]}"
    )


def test_every_edge_type_is_explained_in_the_legend(model):
    """The legend now shows only what the current graph draws, which is a good
    reason to be strict here: an edge type in no legend entry can be on screen
    with nothing anywhere that says what it means."""
    legend = _block(model, "LEGEND_EDGES")
    missing = [t for t in EdgeType if f"'{t.value}'" not in legend]
    assert not missing, (
        f"edge types drawn with no legend entry to explain them: "
        f"{[t.value for t in missing]}"
    )


def test_the_discounting_edges_are_not_filed_under_structural(model):
    """They are the argument, not bookkeeping. Covering them by folding them
    into the structural catch-all would satisfy the test above while undoing
    the thing it exists to protect."""
    legend = _block(model, "LEGEND_EDGES")
    structural = re.search(r"key: 'structural'.*?\}", legend, re.S)
    assert structural, "no structural legend entry"
    for edge in ("parallel_of", "descends_from", "contradicts", "attests"):
        assert f"'{edge}'" not in structural.group(0), (
            f"`{edge}` carries evidential weight and must not be filed as structural"
        )


def test_the_question_column_is_last(model):
    """The rightmost column reads as where the chain arrives. Audit before it,
    because a query is how an assertion was reached, not what it was for."""
    keys = re.findall(r"key: '(\w+)', label:", _block(model, "COLUMNS"))
    assert keys[-1] == "question", f"question is not the terminal column: {keys}"
    assert keys.index("audit") == len(keys) - 2


def test_every_test_outcome_the_api_can_report_has_a_rendering(model):
    """`views.test_outcome` returns one of four strings and the graph view
    styles by it. A value with no entry falls back to "unrun" and silently
    draws a decided prediction as an open one — the same class of bug as a node
    type with no column, and invisible in exactly the same way."""
    from cohort.views import test_outcome  # noqa: F401  (import proves it exists)

    emitted = {"held", "broke", "undecided", "unrun"}
    block = _block(model, "TEST_OUTCOME")
    missing = [o for o in sorted(emitted) if f"{o}:" not in block]
    assert not missing, f"outcomes with no rendering: {missing}"


def test_a_run_prediction_is_not_drawn_as_an_open_one(model):
    """Dotted means "not yet asked". A decided test that kept the dotted style
    would report twenty-two identical lines for twenty-two different results."""
    block = _block(model, "TEST_OUTCOME")
    for outcome in ("held", "broke"):
        line = next(l for l in block.splitlines() if l.strip().startswith(outcome))
        assert "e-tests" not in line, (
            f"{outcome} reuses the unrun style, so a run prediction still "
            "draws as an open one"
        )


# --- one word for the pair ---------------------------------------------------

GRAPH_VIEW = SRC / "GraphView.jsx"


def test_the_node_legend_calls_the_pair_a_hypothesis(model):
    """`claim` and `conjecture` are two node types, and the legend's colours
    apply to both. Calling that pair "claim" was wrong twice: it is the name of
    one of the two, and the Findings page has always called them hypotheses —
    so the same node was a claim on one tab and a hypothesis on another.

    The types themselves stay: they carry different rules (a claim needs an
    attested passage, a conjecture needs a query that would refute it), a
    refusal still names which, and `StatsBar` still counts them separately.
    This is only about the word used where the UI means *either of them*.
    """
    src = GRAPH_VIEW.read_text(encoding="utf-8")
    keys = re.findall(r"\{ key: '([^']+)'", src)
    pair_entries = [k for k in keys if k.split(" —")[0] in {"claim", "conjecture", "hypothesis"}]
    assert pair_entries, "no legend entry for a claim/conjecture colour at all"
    wrong = [k for k in pair_entries if not k.startswith("hypothesis")]
    assert not wrong, (
        f"these legend entries name the pair after one of its members: {wrong}. "
        "Where the UI means a claim *or* a conjecture, it says hypothesis."
    )


def test_no_panel_says_claim_and_conjecture_as_a_collective(model):
    """The phrase itself, in prose. Allowed exactly where it is *teaching* the
    two types — TabIntro glosses "hypotheses (claims and conjectures)" once so
    a reader meets the vocabulary — and nowhere else, because everywhere else
    it is the long way of saying hypothesis."""
    offenders = []
    for path in sorted(SRC.glob("*.jsx")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"[Cc]laims? and conjectures?", src):
            line = src[: m.start()].count("\n") + 1
            window = src[max(0, m.start() - 60): m.end() + 20]
            # a gloss attaches the pair to the word it defines
            if "hypothes" in window.lower():
                continue
            offenders.append(f"{path.name}:{line} {m.group(0)!r}")
    assert not offenders, (
        "these read as the collective noun rather than as a gloss:\n  "
        + "\n  ".join(offenders)
        + "\nSay 'hypothesis', or keep the pair only where it is defining them."
    )
