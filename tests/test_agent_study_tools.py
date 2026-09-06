"""What an agent is offered, and when.

The four ascription tools are the *method* for an attribution question:
register a prediction, survive a negative control, only then speak about a work
in doubt. They are offered only when the server was started against a study,
and the conditional is the point — a worker on a graph with no catalogue would
meet a tool that can do nothing but refuse, and spend a paid turn learning
that.

These are text- and wiring-level checks rather than live runs. Nothing here
calls OpenRouter; `scripts/` holds the manual live-API scripts and the suite
never runs them.
"""
from __future__ import annotations

import pytest

from cohort.agents.attestation_worker import (
    STUDY_TOOLS,
    TOOLS,
    AttestationWorker,
    _STUDY_TOOL_NAMES,
    _study_context,
)
from cohort.agents.review_worker import ReviewWorker
from cohort.attribution import load_study
from cohort.catalogue import load_catalogue
from cohort.delta import DEFAULT_MIN_CHARS

PAD = DEFAULT_MIN_CHARS
KEY = "sk-test-not-a-real-key"
MODEL = "openai/gpt-4o-mini"


def write(root, work, text):
    d = root / work
    d.mkdir(parents=True, exist_ok=True)
    (d / "大.txt").write_text(text, encoding="utf-8")


@pytest.fixture
def study(tmp_path):
    root = tmp_path / "T-stripped"
    for i in range(5):
        write(root, f"B{i}", ("阿黎耶" * (PAD + i * 400)) + ("甲乙丙丁戊"[i] * PAD))
    for i in range(2):
        write(root, f"D{i}", ("阿黎耶" * (PAD + i * 300)) + ("己庚"[i] * PAD))
    for i in range(2):
        write(root, f"C{i}", ("波羅蜜" * (PAD + i * 300)) + ("辛壬"[i] * PAD))
    for i in range(6):
        write(root, f"X{i}", ("多阿含" * PAD) + ("癸子丑寅卯辰"[i] * PAD))

    cat = tmp_path / "cat.txt"
    cat.write_text(
        "B0 bench\nB1 bench\nB2 bench\nB3 bench\nB4 bench\n"
        "D0 weird\nD1 weird\nC0 control\nC1 control\n",
        encoding="utf-8",
    )
    s = load_study(root, load_catalogue(cat, benchmark_label="bench",
                                        control_label="control"))
    yield s
    s.corpus.close()


class _Source:
    def search(self, query, *, max_results=5):
        return []

    def fetch(self, ref):
        raise KeyError(ref)


def worker(graph, **kw):
    return AttestationWorker(
        graph, _Source(), authored_by="agent:worker-1", model=MODEL,
        api_key=KEY, **kw,
    )


def names(tools):
    return {t["function"]["name"] for t in tools}


# --- what is on the table ---------------------------------------------------

def test_a_worker_without_a_study_is_offered_none_of_them(graph):
    w = worker(graph)
    assert names(w.tools) == names(TOOLS)
    assert not names(w.tools) & _STUDY_TOOL_NAMES


def test_a_worker_with_a_study_is_offered_all_four(graph, study):
    w = worker(graph, study=study)
    assert names(w.tools) == names(TOOLS) | _STUDY_TOOL_NAMES


def test_the_class_attribute_stays_the_role_the_instance_carries_the_extension(
    graph, study,
):
    """`TOOLS` is what makes a worker *this role*, and a subclass declares its
    own (`ReviewWorker` does). Whether a study is open is a property of the
    server, not of the role — so it must not mutate the class."""
    worker(graph, study=study)
    assert names(AttestationWorker.TOOLS) == names(TOOLS)
    assert not names(ReviewWorker.TOOLS) & _STUDY_TOOL_NAMES


def test_every_registered_study_tool_has_a_dispatch_case(graph, study):
    """A tool added to the schema list without a dispatch case would reach the
    model, be called, and come back as 'unknown study tool' — which reads like
    the model hallucinated a name it was actually handed."""
    w = worker(graph, study=study)
    for name in sorted(_STUDY_TOOL_NAMES):
        is_error, result = w._dispatch(name, {}, None)
        # Every one refuses on its arguments (none were given), which is the
        # proof it reached a real handler rather than falling through.
        assert is_error, name
        assert "unknown" not in str(result).lower(), name


def test_calling_one_without_a_study_says_what_is_missing(graph):
    """Reachable if a tool name is replayed against a differently-configured
    server. The message has to name the missing configuration, not the rule."""
    w = worker(graph)
    is_error, result = w._dispatch("run_control_test", {"conjecture_id": "x"}, None)
    assert is_error
    assert "ascription study" in str(result)


# --- what the model is told -------------------------------------------------

def test_the_prompt_names_the_groups_so_a_label_need_not_be_guessed(study):
    """`apply_to_disputed` takes a catalogue label as an argument, and a label
    is a researcher's choice that no model can infer. A wrong one is a refusal
    that teaches nothing."""
    text = _study_context(study)
    assert "bench" in text and "control" in text and "weird" in text


def test_the_prompt_states_the_order_and_that_failure_is_a_result(study):
    """Registering after seeing the numbers is the error the whole ordering
    exists to prevent, so the prompt has to say so rather than rely on the
    refusal arriving later."""
    text = _study_context(study)
    assert "negative control" in text
    assert "lower threshold" in text


def test_no_study_means_no_study_paragraph(graph):
    assert _study_context(None) == ""


def test_no_tool_count_is_asserted_in_the_system_prompt():
    """The prompt said "exactly three tools" while six were registered, and had
    been wrong for three stages. A count in prose is a fact that rots — the
    schema list is the only place the number should live.

    Checked as "no number followed by 'tools'" rather than as the one wrong
    sentence, so the next person to write a count is caught too. (This test's
    own first draft asserted `len(STUDY_TOOLS) == 4` and broke on the very next
    tool added, which is the same mistake one layer out.)"""
    words = ("one", "two", "three", "four", "five", "six", "seven", "eight",
             "nine", "ten", "exactly")
    prompt = AttestationWorker.SYSTEM_PROMPT.lower()
    for w in (*words, *(str(i) for i in range(1, 21))):
        assert f"{w} tools" not in prompt, f"the prompt states a tool count: {w!r}"
