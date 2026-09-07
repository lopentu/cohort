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


def _message_locals(tree: ast.AST) -> dict[int, set[str]]:
    """Per function, the local names that were assigned a string.

    `msg = f"..."` followed by `raise SomeError(msg)` states a reason perfectly
    well, and it is the form ruff's EM rules ask for. Without this the check
    reads the second line alone, calls a real message a bare identifier, and
    pushes whoever hits it towards inlining the string to satisfy a test —
    which is the guard bullying code that was already correct.

    Keyed by the enclosing function's `id()` and resolved per function rather
    than per module, so a name that carries a message in one place cannot
    excuse an unrelated parameter of the same name somewhere else.
    """
    out: dict[int, set[str]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names: set[str] = set()
        for node in ast.walk(fn):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None:
                continue
            spelled = (
                isinstance(value, ast.JoinedStr)
                or (isinstance(value, ast.Constant) and isinstance(value.value, str))
                or isinstance(value, (ast.BinOp, ast.Call))
            )
            if not spelled:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
        out[id(fn)] = names
    return out


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    locals_by_fn = _message_locals(tree)
    # which function each call sits in, so a name is resolved in its own scope
    owner: dict[int, int] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner.setdefault(id(node), id(fn))

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
            continue
        arg = node.args[0]
        if not _bare(arg):
            continue
        spelled_here = locals_by_fn.get(owner.get(id(node), -1), set())
        if isinstance(arg, ast.Name) and arg.id in spelled_here:
            continue
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


def test_a_message_assigned_to_a_local_is_not_a_bare_identifier(tmp_path):
    """`msg = f"..."` then `raise X(msg)` states a reason, and it is the form
    ruff's EM rules ask for. The check read the second line alone until
    2026-09-07 and called two real messages bare — found when this guard first
    ran over code merged from another branch."""
    p = tmp_path / "m.py"
    p.write_text(
        "from cohort.errors import UnitNotInCorpus\n"
        "def f(uid):\n"
        '    msg = f"{uid} has no base text in the corpus"\n'
        "    raise UnitNotInCorpus(msg)\n",
        encoding="utf-8",
    )
    assert _offenders(p) == []


def test_a_bare_parameter_is_still_caught_in_the_same_shape(tmp_path):
    """The other half: resolving locals must not excuse the thing this exists
    to catch, even in a function that also spells a message somewhere."""
    p = tmp_path / "m.py"
    p.write_text(
        "from cohort.errors import UnitNotInCorpus\n"
        "def f(uid, other):\n"
        '    msg = f"{uid} has no base text"\n'
        "    if other:\n"
        "        raise UnitNotInCorpus(other)\n"
        "    raise UnitNotInCorpus(msg)\n",
        encoding="utf-8",
    )
    assert [o.split()[-2:] for o in _offenders(p)] == [["UnitNotInCorpus(<bare", "identifier>)"]]


def test_a_name_carrying_a_message_in_one_function_does_not_excuse_another(tmp_path):
    """Resolution is per function, not per module: `msg` meaning a message in
    one place must not make a `msg` parameter elsewhere acceptable."""
    p = tmp_path / "m.py"
    p.write_text(
        "from cohort.errors import UnitNotInCorpus\n"
        "def a():\n"
        '    msg = f"a real reason"\n'
        "    raise UnitNotInCorpus(msg)\n"
        "def b(msg):\n"
        "    raise UnitNotInCorpus(msg)\n",
        encoding="utf-8",
    )
    assert len(_offenders(p)) == 1
