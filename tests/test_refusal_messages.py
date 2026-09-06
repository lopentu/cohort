"""A refusal has to say why.

`POST /api/attest` returns `{"rule": ..., "message": str(error)}`, and the
researcher UI prints exactly that. So an error carrying only a node id reaches
a person as `UnattestableClaim: claim:aa72d5bb…` — a rule name and an opaque
identifier, with nothing about what is missing or what would fix it.

This is not hypothetical twice over. The same defect on `NodeNotFound` cost a
live run five refusals on 2026-09-01: three models on three families all
guessed at an id because the message told them nothing, which is what
`_unfound_detail` was added for. And the attest preconditions were found the
same way on 2026-09-02, by walking the ladder over HTTP rather than by any
test — every unit test asserted the *type* of the refusal and none read what it
said.

So: a scan, not a list of cases. A message that is only an identifier fails
here regardless of which error it belongs to.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cohort import errors as errors_mod

ROOT = Path(__file__).parent.parent / "cohort"

COHORT_ERRORS = {
    name for name, obj in vars(errors_mod).items()
    if isinstance(obj, type) and issubclass(obj, errors_mod.CohortError)
}

#: Errors whose whole meaning is the name, with nothing useful to add.
#: Each needs a reason, which is what keeps this from becoming a place to
#: silence the check.
EXEMPT: dict[str, str] = {
    # SingleWriterViolation is raised by the lock itself, before any node is in
    # hand; there is no id to name and the class docstring is the explanation.
    "SingleWriterViolation": "raised by the lock, with no subject to describe",
    # Its one argument *is* the message: the whole node/edge diff between the
    # projection and a replay of the log. Nothing to add, and prose in front of
    # it would push the diff off the first screen.
    "RebuildMismatch": "its argument is the diff itself, which is the answer",
}


def _bare(node: ast.expr) -> bool:
    """True when the argument carries no prose: a lone name, attribute, or an
    f-string that is only an interpolation."""
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        return True
    if isinstance(node, ast.JoinedStr):
        return all(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # a short literal that is just an id-shaped token
        return len(node.value.split()) < 3
    return False


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if name not in COHORT_ERRORS or name in EXEMPT:
            continue
        if not node.args:
            out.append(f"{path.name}:{node.lineno} {name}() with no message")
        elif _bare(node.args[0]):
            out.append(f"{path.name}:{node.lineno} {name}(<bare identifier>)")
    return out


@pytest.mark.parametrize(
    "path",
    sorted(p for p in ROOT.rglob("*.py") if p.name != "errors.py"),
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_every_refusal_states_a_reason(path):
    offenders = _offenders(path)
    assert not offenders, (
        "these refusals reach a researcher as a rule name and an opaque id:\n  "
        + "\n  ".join(offenders)
        + "\nSay what is missing and what would fix it."
    )


def test_the_scan_recognises_a_bare_message():
    """The guard is only worth having if it fails on the shape it was written
    for, so the shape is checked directly."""
    assert _bare(ast.parse("x", mode="eval").body)
    assert _bare(ast.parse("f'{node_id}'", mode="eval").body)
    assert _bare(ast.parse("'claim:abc'", mode="eval").body)
    assert not _bare(ast.parse("f'{node_id} has no attesting passage'", mode="eval").body)
