"""The negative control: does the system ever catch anything?

Every live demonstration in this repository so far has been given honest
input, and each one shows COHORT recording something correctly. None of them
shows it *refusing* something that looked fine. That asymmetry is the first
thing a reader should be suspicious of, so this script supplies the other half.

The claim below is grounded, cited, and every citation resolves — except one,
whose stored excerpt has been altered by a single character. A real reviewer on
another model family is then asked to check it. Promotion rests on the
mechanical re-fetch, so whatever verdict the model returns, the claim must not
advance.

What is deliberately *not* tampered with is the payload hash: it is recomputed
after the edit, so `verify_integrity()` comes back clean. That isolates the
span re-fetch as the only thing standing between a plausible-looking claim and
`attested`. If integrity checking were doing the work here, the demonstration
would be about a different mechanism.

The mechanism itself is already unit-tested with a synthetic passage
(`tests/test_reviewer.py::test_a_model_verdict_cannot_promote_a_claim_whose_spans_fail`).
What this adds is real corpus bytes, a real archive read, and a real model
writing a real verdict — none of which a test may do.

Never imported by pytest, never run automatically — same discipline as
`scripts/run_swarm_demo.py`.

Usage:
    .venv/bin/python scripts/run_negative_control.py
    .venv/bin/python scripts/run_negative_control.py --db nc.sqlite --budget 0.05

Costs about $0.002: one reviewer, a handful of turns. Requires
CBETA_ARCHIVE_PATH, OPENROUTER_API_KEY and OPENROUTER_MODEL (see .env.example).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import NoReturn

from cohort.agents.openrouter import _load_dotenv, load_model_pool
from cohort.families import model_family
from cohort.graph import Graph
from cohort.schemas import AgentKind, AgentProfile, NodeStatus, VerificationResult
from cohort.sources.env import open_corpus_from_env
from cohort.tools.find_attestations import FindAttestationsInput, find_attestations
from cohort.tools.propose_claim import ProposeClaimInput, propose_claim

REPO_ROOT = Path(__file__).resolve().parent.parent

PLANTER = "agent:planter"
REVIEWER = "agent:negative-control-reviewer"

#: A claim the corpus does support, so that everything except the planted
#: defect is genuine. The point is a citation that fails to re-verify, not a
#: claim that was never grounded — `propose_claim` already refuses those.
CLAIM_TEXT = "The title 般若波羅蜜多心經 appears in the corpus."
GROUNDING_QUERY = "般若波羅蜜多心經"


def die(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def tamper(graph: Graph, passage_id: str) -> tuple[str, str]:
    """Alter one character of a stored excerpt, then re-hash.

    Written straight into the projection on purpose. There is no tool for
    this and there should not be: no agent may edit a recorded excerpt, which
    is why a *fabricated* citation cannot be written through the boundary at
    all. What this models is the other case — a citation that was honest when
    recorded and no longer resolves, because the source moved under it or the
    projection was restored from something untrustworthy.

    Re-hashing is what makes the demonstration honest. Leave the hash alone
    and `verify_integrity()` catches the edit immediately, and the run would
    be showing off a different mechanism than the one it claims to test.
    """
    row = graph.conn.execute(
        "SELECT payload FROM nodes WHERE id=?", (passage_id,)
    ).fetchone()
    payload = json.loads(row["payload"])
    original = payload["excerpt"]
    # One character, in the middle, so the excerpt still looks entirely
    # plausible to anyone reading the record rather than re-fetching it.
    i = len(original) // 2
    altered = original[:i] + ("龍" if original[i] != "龍" else "虎") + original[i + 1:]
    payload["excerpt"] = altered

    # Serialised the way `_apply_propose` serialises it, so the recomputed
    # hash matches the projection's own convention. A different encoding would
    # fail integrity for the wrong reason and quietly turn this into a demo of
    # payload hashing.
    payload_json = json.dumps(payload)
    graph.conn.execute(
        "UPDATE nodes SET payload=?, payload_hash=? WHERE id=?",
        (payload_json, hashlib.sha256(payload_json.encode("utf-8")).hexdigest(), passage_id),
    )
    graph.conn.commit()
    return original, altered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(REPO_ROOT / "negative_control.sqlite"))
    parser.add_argument("--budget", type=float, default=0.05, help="hard USD cap")
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--reviewer-model", default=None,
                        help="must be a different provider from --planter-model")
    parser.add_argument("--planter-model", default=None,
                        help="the family the planted claim is attributed to")
    parser.add_argument("--force", action="store_true",
                        help="discard an existing graph at --db. Without it an "
                             "existing one is left alone: a live run's log is the "
                             "artifact, not scratch space")
    args = parser.parse_args()

    _load_dotenv(REPO_ROOT / ".env")
    source, reason = open_corpus_from_env(repo_root=REPO_ROOT)
    if source is None:
        die(f"corpus unavailable — {reason}")

    pool = load_model_pool()
    planter_model = args.planter_model or (pool[0] if pool else "")
    reviewer_model = args.reviewer_model or next(
        (m for m in pool if model_family(m) != model_family(planter_model)), ""
    )
    if not reviewer_model:
        die("no second model family available; set OPENROUTER_MODELS or pass "
            "--reviewer-model (a reviewer on the author's own family is refused)")

    db_path = Path(args.db)
    log_path = db_path.with_suffix(".jsonl")
    if db_path.exists() or log_path.exists():
        # A live run's log is the artifact. This script overwrote one on
        # 2026-09-02 and the record of the sharpest result it has produced —
        # a model returning `sound` over a citation that did not re-verify —
        # survives only as a console transcript. Not again by default.
        if not args.force:
            die(f"{db_path.name} already exists. Pass --force to discard it, or "
                f"--db to write somewhere else. A live run's log is the artifact.")
        for p in (db_path, log_path, Path(str(db_path) + ".lock")):
            if p.exists():
                p.unlink()

    print(f"planting as {planter_model}, reviewing with {reviewer_model}\n")

    # --- plant ---------------------------------------------------------------
    graph = Graph.open(db_path, log_path)
    graph.register_agent(
        AgentProfile(id=PLANTER, kind=AgentKind.WORKER,
                     corpus_scope="the planted claim only",
                     method_label="setup for a negative control", model=planter_model),
        authored_by=PLANTER,
    )
    claim_id = propose_claim(
        graph, source,
        ProposeClaimInput(text=CLAIM_TEXT, grounding_query=GROUNDING_QUERY),
        authored_by=PLANTER,
    )
    report = find_attestations(
        graph, source,
        FindAttestationsInput(claim_or_conjecture_id=claim_id, query=GROUNDING_QUERY,
                              max_results=5),
        authored_by=PLANTER,
    )
    if not report.passages:
        die("the grounding query found nothing to cite; nothing to tamper with")

    target = report.passages[0]
    original, altered = tamper(graph, target)
    print(f"claim   {claim_id}\n        {CLAIM_TEXT}")
    print(f"cited   {len(report.passages)} passage(s)")
    print(f"altered {target}")
    print(f"        {original!r}\n     -> {altered!r}")

    integrity = graph.verify_integrity()
    print(f"\nintegrity: {integrity.checked} payload(s) checked, "
          f"{len(integrity.mismatched)} mismatched")
    if integrity.mismatched:
        die("the tamper left an integrity mismatch, so this would demonstrate "
            "payload hashing rather than span re-verification")
    print("        the record looks clean. Only a re-fetch can catch this.\n")
    graph.close()

    # --- review --------------------------------------------------------------
    from cohort.ui.runs import ROLE_REVIEWER, AgentSpec, RunManager, RunRejected

    manager = RunManager(db_path, log_path, source,
                         max_budget_usd=args.budget, max_turns=args.max_turns)
    try:
        started = manager.start(
            [AgentSpec(
                agent_id=REVIEWER,
                instructions=(
                    "Review the claim awaiting review. Re-check its citations and "
                    "give your verdict."
                ),
                corpus_scope="whatever the claim cites",
                method_label="citation re-verification",
                model=reviewer_model, role=ROLE_REVIEWER,
            )],
            budget_usd=args.budget, max_turns=args.max_turns,
        )
    except RunRejected as e:
        die(str(e))

    while True:
        current = manager.current()
        if not current or current["state"] not in ("starting", "running"):
            break
        time.sleep(0.5)
    run = manager.get(started["id"]) or {}
    spend = run.get("spend", {})
    print(f"run {started['id']}  {run.get('state')}  "
          f"${spend.get('spent_usd', 0):.5f}  {spend.get('calls', 0)} call(s)")
    for entry in run.get("tool_calls", []):
        mark = "refused" if entry.get("is_error") else "ok"
        print(f"  [{mark}] {entry['tool']}: {str(entry.get('result'))[:100]}")

    # --- the result ----------------------------------------------------------
    graph = Graph.open_read_only(db_path)
    try:
        claim = graph.get_node(claim_id)
        reviews = [
            v for v in graph.verifications(claim_id)
            if v.payload.get("detail", "").startswith("reviewer")
        ]
        print(f"\nclaim status: {claim.status}")
        for v in reviews:
            print(f"  verification {v.id}")
            print(f"    result:      {v.payload['result']}")
            print(f"    detail:      {v.payload.get('detail')}")
            print(f"    limitations: {v.payload.get('limitations')}")

        held = claim.status == NodeStatus.PROPOSED
        failed = any(v.payload["result"] == VerificationResult.FAIL for v in reviews)
        print()
        if held and failed:
            print("PASS — the citation did not re-verify and the claim did not advance.")
            print("       Promotion rests on the re-fetch, not on what the model said.")
        elif held:
            print("HELD, but no verification recorded a failure — read the run above; "
                  "the reviewer may never have reached the claim.")
        else:
            print("FAIL — the claim advanced with a citation that does not re-verify. "
                  "That is the property this script exists to check.")
            sys.exit(1)
    finally:
        graph.close()

    print(f"\n  cohort --db {db_path.name} run --history")
    print(f"  cohort --db {db_path.name} refusals --run {started['id']} --census")


if __name__ == "__main__":
    main()
