"""CLI and web UI must expose the same capabilities.

COHORT promises it can be driven two ways — as a library/CLI by people who
write Python, and through a browser by researchers who don't. That promise
decays silently: someone adds a route and forgets the command, or the other way
round, and nothing complains until a user finds the hole.

So the promise is a test. Every HTTP route maps to a CLI command and every CLI
command maps to a route, and adding either without the other fails here. A
deliberate asymmetry is allowed, but it has to be written into `EXEMPT` with a
reason — which makes it a decision rather than an oversight.
"""
from __future__ import annotations

import argparse

import pytest

from cohort.cli import build_parser
from cohort.eventlog import EventLog
from cohort.graph import Graph
from cohort.ui.api import create_app
from cohort.ui.runs import RunManager

# Route -> CLI command. One entry per HTTP route, with every capability the
# browser has named on the left and the terminal equivalent on the right.
ROUTE_TO_COMMAND = {
    ("GET", "/api/health"): "health",
    ("GET", "/api/graph"): "graph",
    ("GET", "/api/node"): "node",
    ("GET", "/api/citable"): "citable",
    ("GET", "/api/ledger"): "ledger",
    ("GET", "/api/rejected"): "rejected",
    ("GET", "/api/agent"): "agent",
    ("GET", "/api/refusals"): "refusals",
    ("GET", "/api/findings"): "findings",
    ("GET", "/api/questions"): "question",
    ("POST", "/api/questions"): "question",
    ("GET", "/api/integrity"): "integrity",
    ("GET", "/api/rebuild"): "rebuild",
    ("POST", "/api/attest"): "attest",
    ("POST", "/api/test-conjecture"): "test-conjecture",
    ("POST", "/api/edge/retract"): "retract-edge",
    ("POST", "/api/edge/restore"): "restore-edge",
    ("POST", "/api/accept"): "accept",
    ("POST", "/api/reject"): "reject",
    ("POST", "/api/reopen"): "reopen",
    ("GET", "/api/corpus/search"): "search",
    ("GET", "/api/corpus/fetch"): "fetch",
    # The web launcher is asynchronous because a browser cannot block, so it
    # needs separate routes to poll and to stop. A terminal can block, so one
    # foreground `run` command covers all four: it waits, prints the same
    # report, and Ctrl-C is the stop button.
    ("GET", "/api/run/config"): "run",
    ("GET", "/api/run"): "run",
    ("GET", "/api/run/{run_id}"): "run",
    ("POST", "/api/run"): "run",
    ("POST", "/api/run/stop"): "run",
}

#: Capabilities deliberately on one side only. Each needs a reason, not just an
#: entry — an exemption without one is the drift this test exists to catch.
EXEMPT: dict[str, str] = {
    # Nothing yet. Corpus index building and the parser scan are scripts rather
    # than CLI commands, but they are not web capabilities either, so they are
    # symmetric by absence and need no exemption here.
}


@pytest.fixture
def app_routes(tmp_path):
    """Every route the API can mount, with all three capabilities enabled —
    a partially-enabled app would let a missing command pass unnoticed."""
    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    Graph(db, event_log=EventLog(log)).close()

    class _Source:
        def search(self, query, *, max_results=5):
            return []

        def fetch(self, ref):
            raise KeyError(ref)

    source = _Source()
    app = create_app(
        db, log, allow_writes=True, source=source,
        run_manager=RunManager(db, log, source),
    )
    routes = set()
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        if not path.startswith("/api"):
            continue
        for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            routes.add((method, path))
    return routes


def cli_commands() -> set[str]:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def test_every_http_route_has_a_cli_command(app_routes):
    """A capability in the browser that the terminal cannot reach."""
    unmapped = sorted(r for r in app_routes if r not in ROUTE_TO_COMMAND)
    assert not unmapped, (
        f"HTTP routes with no CLI equivalent: {unmapped}. Add the command to "
        f"cohort/cli.py and map it in ROUTE_TO_COMMAND, or record why it is "
        f"web-only in EXEMPT."
    )


def test_every_cli_command_has_an_http_route(app_routes):
    """A capability in the terminal that the browser cannot reach."""
    mapped = set(ROUTE_TO_COMMAND.values())
    orphans = sorted(c for c in cli_commands() if c not in mapped and c not in EXEMPT)
    assert not orphans, (
        f"CLI commands with no HTTP equivalent: {orphans}. Add the route to "
        f"cohort/ui/api.py, or record why it is terminal-only in EXEMPT."
    )


def test_route_map_references_only_real_routes(app_routes):
    """The map itself must not rot: a renamed route should fail loudly here
    rather than leaving a stale entry that silently satisfies the check."""
    stale = sorted(r for r in ROUTE_TO_COMMAND if r not in app_routes)
    assert not stale, f"ROUTE_TO_COMMAND names routes that no longer exist: {stale}"


def test_route_map_references_only_real_commands():
    commands = cli_commands()
    stale = sorted({c for c in ROUTE_TO_COMMAND.values() if c not in commands})
    assert not stale, f"ROUTE_TO_COMMAND names commands that no longer exist: {stale}"


def test_exemptions_carry_a_reason():
    blank = sorted(k for k, v in EXEMPT.items() if not v.strip())
    assert not blank, f"exemptions without a stated reason: {blank}"
