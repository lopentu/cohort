"""The terminal front end, deliberately the same surface as the web one.

COHORT is meant to be usable two ways — as a Python library by people who write
Python, and as a tool by researchers who don't. That promise is only kept if
the two front ends can do the same things, so every command here corresponds to
a route in `cohort/ui/api.py`, and `tests/test_parity.py` fails the build if one
gains a capability the other lacks. Where a correspondence is deliberately not
one-to-one, the exemption is written down there rather than left to be noticed.

Both front ends sit on the same library calls. Neither reimplements a rule:
`accept` here and `POST /api/accept` both call `Graph.accept()`, so the write
boundary refuses identically whichever way you reach it.

    cohort health
    cohort graph --type claim
    cohort node claim:abc123
    cohort accept claim:abc123
    cohort reject claim:abc123 --reason "conflates two recensions"
    cohort refusals
    cohort rebuild
    cohort search 色即是空
    cohort run --agent "find attestations for 色即是空" --budget 0.05

`--json` on any command prints exactly what the corresponding HTTP route
returns, which is what makes the parity claim checkable rather than asserted.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from .attribution import FEATURE_SETS
from .errors import (
    CohortError,
    EdgeNotFound,
    NodeNotFound,
    RebuildMismatch,
    SingleWriterViolation,
)
from .eventlog import EventLog, read_refusals, read_runs, summarize_refusals
from .graph import Graph
from .schemas import RESEARCHER, EdgeType, NodeType, QuestionPayload
from .views import (
    dossier_json,
    edge_json,
    findings_json,
    locate_passage_span,
    node_detail_json,
    node_json,
    question_json,
    questions_json,
    verified_span_for,
)

DEFAULT_DB = "demo_graph.sqlite"


# --- plumbing ---------------------------------------------------------------

def _log_path(args) -> Path:
    """Default the event log beside the projection, same rule the server uses."""
    return Path(args.log) if args.log else Path(args.db).with_suffix(".jsonl")


def _read(args) -> Graph:
    """A reader's handle: no writer lock, so this works while a run is writing."""
    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(
            f"no graph at {db}. Build one with scripts/seed_demo_graph.py, "
            f"or point at another with --db"
        )
    return Graph.open_read_only(db)


def _write(args) -> Graph:
    """A writer's handle, held for one command. If an agent run holds the lock
    this raises rather than waiting — the same answer the API gives as a 409."""
    return Graph(Path(args.db), event_log=EventLog(_log_path(args)))


def _emit(args, payload: Any, render) -> None:
    """`--json` prints the API's own shape; otherwise render for a human."""
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render(payload)


def _corpus(args):
    from .sources.env import open_corpus_from_env
    source, reason = open_corpus_from_env(repo_root=Path.cwd())
    if source is None:
        raise SystemExit(f"corpus unavailable: {reason}")
    return source


# --- read commands ----------------------------------------------------------

def cmd_health(args) -> None:
    graph = _read(args)
    try:
        counts = {
            r["type"]: r["c"]
            for r in graph.conn.execute("SELECT type, COUNT(*) c FROM nodes GROUP BY type")
        }
        edges = graph.conn.execute("SELECT COUNT(*) c FROM edges").fetchone()["c"]
    finally:
        graph.close()
    payload = {"ok": True, "db_path": args.db, "nodes": counts, "edges": edges}

    def render(p):
        print(f"{p['db_path']}  —  {sum(p['nodes'].values())} nodes, {p['edges']} edges")
        for t, n in sorted(p["nodes"].items(), key=lambda kv: -kv[1]):
            print(f"  {n:>6}  {t}")
    _emit(args, payload, render)


def cmd_graph(args) -> None:
    graph = _read(args)
    try:
        node_type = NodeType(args.type) if args.type else None
        nodes = graph.nodes(node_type=node_type, limit=args.limit + 1)
        truncated = len(nodes) > args.limit
        nodes = nodes[: args.limit]
        ids = {n.id for n in nodes}
        edges = [
            e for e in graph.edges(include_retracted=args.include_retracted)
            if e.src in ids and e.dst in ids
        ]
        payload = {
            "nodes": [node_json(graph, n) for n in nodes],
            "edges": [edge_json(e) for e in edges],
            "truncated": truncated,
        }
    finally:
        graph.close()

    def render(p):
        for n in p["nodes"]:
            print(f"{n['status']:<9} {n['type']:<12} {n['id']}")
        print(f"\n{len(p['nodes'])} nodes, {len(p['edges'])} edges", end="")
        # Truncation is stated, never silent: a cut graph shows less support
        # than exists, which here changes what the result appears to say.
        print("  (TRUNCATED — pass --limit for more)" if p["truncated"] else "")
    _emit(args, payload, render)


def cmd_node(args) -> None:
    graph = _read(args)
    try:
        payload = node_detail_json(graph, args.id, log_path=_log_path(args))
    except NodeNotFound as e:
        raise SystemExit(str(e)) from e
    finally:
        graph.close()

    def render(p):
        print(f"{p['id']}\n  type       {p['type']}\n  status     {p['status']}")
        print(f"  assurance  {p['assurance']}")
        if p.get("rejected_reason"):
            print(f"  rejected   {p['rejected_reason']}")
        for k, v in (p.get("payload") or {}).items():
            print(f"  {k:<10} {v}")
        sup = p.get("independent_support")
        if sup:
            # The whole argument in one line: a support count means nothing
            # without the independence flag beside it.
            flag = "independent" if sup["independent"] else "NOT independent (shared descent)"
            print(f"  support    {sup['attesting_count']} attesting, "
                  f"{sup['distinct_witnesses']} distinct witness(es) — {flag}")
            for a, b in sup["non_independent_pairs"]:
                print(f"             discounted: {a} ~ {b}")
        for v in p["verifications"]:
            pl = v["payload"]
            print(f"  verified   {pl['method']} -> {pl['result']} | {pl['assurance_level']}")
        for e in p["edges_out"]:
            print(f"  --{e['type']}--> {e['dst']}")
        for e in p["edges_in"]:
            print(f"  <--{e['type']}-- {e['src']}")
    _emit(args, payload, render)


def cmd_citable(args) -> None:
    graph = _read(args)
    try:
        payload = [node_json(graph, n) for n in graph.citable()]
    finally:
        graph.close()

    def render(p):
        if not p:
            # Not an error, and worth saying plainly: nothing is citable until
            # the researcher signs it, so an empty list is the normal state.
            print("nothing is citable yet — only accepted nodes are, and none are accepted")
            return
        for n in p:
            print(f"{n['type']:<12} {n['id']}")
        print(f"\n{len(p)} citable")
    _emit(args, payload, render)


def cmd_rejected(args) -> None:
    graph = _read(args)
    try:
        node_type = NodeType(args.type) if args.type else None
        payload = [node_json(graph, n) for n in graph.rejected(node_type=node_type)]
    finally:
        graph.close()

    def render(p):
        # Rejections with reasons are part of the scholarly output, not a
        # failure list (docs/design.md §8).
        for n in p:
            print(f"{n['type']:<12} {n['id']}\n    {n.get('rejected_reason') or '(no reason recorded)'}")
        print(f"\n{len(p)} rejected")
    _emit(args, payload, render)


def cmd_agent(args) -> None:
    graph = _read(args)
    try:
        payload = graph.agent_report(args.id).model_dump(mode="json")
        profile = graph.agent_profile(args.id)
        payload["profile"] = profile.model_dump(mode="json") if profile else None
    finally:
        graph.close()

    def render(p):
        print(f"{args.id}")
        if p.get("profile"):
            pr = p["profile"]
            print(f"  scope      {pr.get('corpus_scope') or '—'}")
            print(f"  method     {pr.get('method_label') or '—'}")
        for k, v in p.items():
            if k != "profile" and not isinstance(v, (dict, list)):
                print(f"  {k:<10} {v}")
        # Counts, never a score — see docs/design.md §9.
        print("\n  contribution counts, not a reputation score")
    _emit(args, payload, render)


def cmd_refusals(args) -> None:
    log = _log_path(args)
    run_id = getattr(args, "run", None)
    if not log.is_file():
        payload = {
            "available": False, "log_path": str(log), "refusals": [], "total": 0,
            "census": None,
        }
    else:
        allr = read_refusals(log, run_id=run_id)
        shown = allr[-args.limit:]
        payload = {
            "available": True, "log_path": str(log), "run_id": run_id,
            "total": len(allr),
            "truncated": len(shown) < len(allr),
            "refusals": [r.model_dump(mode="json") for r in shown],
            # Over the whole log (or the whole run), never over `shown`: a
            # census of a truncated tail would report a smaller total than the
            # log holds while looking authoritative.
            "census": summarize_refusals(log, run_id=run_id).model_dump(mode="json"),
        }

    def render(p):
        if not p["available"]:
            print(f"no event log at {p['log_path']}, so refusals cannot be read")
            return
        if not args.census:
            for r in p["refusals"]:
                print(f"#{r['seq']:<5} {r['attempted']:<12} {r['rule']}\n      {r['message']}")
            print()
        _render_census(p["census"])
    _emit(args, payload, render)


def _render_census(c: dict) -> None:
    """The summary a researcher reads before deciding which refusals to open.

    Ordered by what it asks of the reader: the count first (a zero is a fact,
    not an absence of news), then the categories that say which bucket to look
    in, then the streaks, which say where to look first."""
    # A zero here is a fact, not an absence of news.
    print(f"{c['total']} refused write(s) — the write boundary holding, not failures")
    if not c["total"]:
        return

    labels = {
        "evidence": "the corpus did not support it",
        "standing": "who was writing, or the node's state, forbade it",
        "expression": "the writer could not say what it meant",
        "operational": "the system's own preconditions",
        "unclassified": "rule unknown to this version's taxonomy",
    }
    for name, n in c["by_category"].items():
        if n:
            print(f"  {n:>4}  {name:<13} {labels.get(name, '')}")
    for rule, n in c["by_rule"].items():
        print(f"        {n:>3} x {rule}")

    if not c["streaks"]:
        return
    print(
        f"\n{len(c['streaks'])} streak(s), {c['streaked_count']} of "
        f"{c['total']} refusals — one agent refused repeatedly by one rule."
    )
    for s in c["streaks"]:
        ids = ", ".join(s["node_ids"][:3]) or "(no node id)"
        more = f" +{len(s['node_ids']) - 3} more" if len(s["node_ids"]) > 3 else ""
        print(
            f"  {s['count']}x {s['rule']} [{s['category']}] "
            f"by {s['authored_by']} calling {', '.join(s['attempted'])} "
            f"(#{s['first_seq']}-{s['last_seq']})\n      tried: {ids}{more}"
        )
    if any(s["category"] == "expression" for s in c["streaks"]):
        # Evidence for a reading, never a verdict: whether a tool is missing
        # is a judgement, and the point of counting is to put it in front of
        # someone who can make it.
        print(
            "\n  A streak in `expression` is worth opening: every one in this\n"
            "  project's history was a gap in the tool layer rather than a model\n"
            "  error — an agent adapting, retrying, and being refused again\n"
            "  because there was no sanctioned way to say what it meant."
        )


def cmd_integrity(args) -> None:
    graph = _read(args)
    try:
        payload = graph.verify_integrity(args.id).model_dump(mode="json")
    finally:
        graph.close()

    def render(p):
        print(f"checked {p['checked']} node payload(s)")
        print(f"  mismatched {len(p['mismatched'])}   unhashed {len(p['unhashed'])}")
        for i in p["mismatched"]:
            print(f"  TAMPERED  {i}")
    _emit(args, payload, render)


def cmd_rebuild(args) -> None:
    log = _log_path(args)
    if not log.is_file():
        payload = {"available": False, "log_path": str(log)}
    else:
        graph = _read(args)
        try:
            payload = {"available": True, "log_path": str(log),
                       **graph.rebuild(log_path=log).model_dump(mode="json")}
        except RebuildMismatch as e:
            payload = {"available": True, "log_path": str(log), "ok": False, "mismatch": str(e)}
        finally:
            graph.close()

    def render(p):
        if not p["available"]:
            print(f"no event log at {p['log_path']}, so the projection cannot be checked")
            return
        if p.get("ok"):
            print(f"OK — replayed {p['events_replayed']} events to "
                  f"{p['nodes']} nodes / {p['edges']} edges, matching this projection")
        else:
            # The log is ground truth, so a mismatch means the database is
            # wrong, not the log (docs/design.md §5 principle 1).
            print("MISMATCH — the projection disagrees with the log, which is ground truth:")
            print(p["mismatch"])
    _emit(args, payload, render)


# --- write commands ---------------------------------------------------------

def _verdict(args, action: str) -> None:
    try:
        graph = _write(args)
    except SingleWriterViolation as e:
        # Same answer the API gives as a 409, phrased for a terminal.
        raise SystemExit(f"the graph is locked by another writer (an agent run?): {e}") from e
    try:
        kwargs: dict[str, Any] = {"authored_by": RESEARCHER}
        if action in ("reject", "reopen"):
            kwargs["reason"] = args.reason
        if action == "attest":
            # Not a verdict: the write boundary runs the mechanical check and
            # refuses if the node has nothing attesting it. No decision node.
            graph.attest(args.id, **kwargs)
            decision_id = None
        else:
            method = {"accept": graph.accept, "reject": graph.reject,
                      "reopen": graph.reopen}[action]
            decision_id = method(args.id, **kwargs)
        payload = {"node": node_json(graph, graph.get_node(args.id)),
                   "decision_node_id": decision_id}
    except NodeNotFound as e:
        raise SystemExit(str(e)) from e
    except CohortError as e:
        # A refused write is a real answer from this system, already recorded
        # to the log. Exit 2 distinguishes it from a usage error.
        print(f"refused ({type(e).__name__}): {e}", file=sys.stderr)
        raise SystemExit(2) from e
    finally:
        graph.close()

    _emit(args, payload, lambda p: print(f"{p['node']['id']} -> {p['node']['status']}"))


def _edge_verdict(args, action: str) -> None:
    try:
        graph = _write(args)
    except SingleWriterViolation as e:
        raise SystemExit(f"the graph is locked by another writer (an agent run?): {e}") from e
    try:
        method = graph.retract_edge if action == "retract" else graph.restore_edge
        method(args.id, authored_by=RESEARCHER, reason=args.reason)
        edge = next(e for e in graph.edges(include_retracted=True) if e.id == args.id)
        payload = {"edge": edge_json(edge)}
    except EdgeNotFound as e:
        raise SystemExit(str(e)) from e
    except CohortError as e:
        print(f"refused ({type(e).__name__}): {e}", file=sys.stderr)
        raise SystemExit(2) from e
    finally:
        graph.close()

    def render(p):
        e = p["edge"]
        state = "retracted" if e["retracted"] else "in force"
        print(f"{e['type']} {e['src']} -> {e['dst']}  ->  {state}")
        if e["retracted_reason"]:
            print(f"  {e['retracted_reason']}")
    _emit(args, payload, render)


def cmd_retract_edge(args) -> None:
    _edge_verdict(args, "retract")


def cmd_restore_edge(args) -> None:
    _edge_verdict(args, "restore")


def cmd_attest(args) -> None:
    _verdict(args, "attest")


def cmd_accept(args) -> None:
    _verdict(args, "accept")


def cmd_reject(args) -> None:
    _verdict(args, "reject")


def cmd_reopen(args) -> None:
    _verdict(args, "reopen")


def cmd_question(args) -> None:
    """Research questions: list them, read one, ask one, or record that a
    claim or conjecture answers one.

    Asking and linking are writes and take the writer's lock; listing does
    not."""
    if args.ask:
        try:
            graph = _write(args)
        except SingleWriterViolation as e:
            raise SystemExit(f"the graph is locked by another writer (an agent run?): {e}") from e
        try:
            qid = graph.ask_question(
                QuestionPayload(text=args.ask, answerable_by=args.answerable_by),
                authored_by=RESEARCHER,
            )
            payload = question_json(graph, qid)
        except CohortError as e:
            raise SystemExit(f"refused ({type(e).__name__}): {e}") from e
        finally:
            graph.close()
    elif args.address:
        if not args.id:
            raise SystemExit("--address needs --id: which question does it answer?")
        try:
            graph = _write(args)
        except SingleWriterViolation as e:
            raise SystemExit(f"the graph is locked by another writer (an agent run?): {e}") from e
        try:
            graph.add_edge(
                EdgeType.ADDRESSES, args.address, args.id, authored_by=RESEARCHER,
            )
            payload = question_json(graph, args.id)
        except NodeNotFound as e:
            raise SystemExit(str(e)) from e
        except CohortError as e:
            raise SystemExit(f"refused ({type(e).__name__}): {e}") from e
        finally:
            graph.close()
    else:
        graph = _read(args)
        try:
            payload = question_json(graph, args.id) if args.id else questions_json(graph)
        except NodeNotFound as e:
            raise SystemExit(str(e)) from e
        finally:
            graph.close()

    def render_list(p):
        if not p["questions"]:
            print("no research questions recorded — `cohort question --ask \"...\"`")
            return
        for q in p["questions"]:
            print(f"{q['id']}")
            print(f"  {q['question']}")
            print(f"  answerable by: {q['answerable_by']}")
            print(f"  {q['addressed_by']} hypothesis/es address it\n")

    def render_one(p):
        print(f"{p['id']}\n\n{p['question']}\n")
        print(f"  answerable by\n    {p['answerable_by']}\n")
        if not p["hypotheses"]:
            print("  nothing has been put forward as an answer yet")
            return
        counts = ", ".join(f"{n} {st}" for st, n in sorted(p["by_status"].items()))
        print(f"  {len(p['hypotheses'])} hypothesis/es — {counts}")
        if p["unsupported"]:
            print(f"  {p['unsupported']} with nothing attesting them")
        if p["discounted"]:
            print(f"  {p['discounted']} whose support is shared descent")
        print("  (a tally, not a verdict — nothing here says the question is answered)\n")
        for h in p["hypotheses"]:
            sup = h["support"]
            state = ("nothing attests it yet" if sup["vacuous"]
                     else "independent" if sup["independent"] else "SHARED DESCENT")
            print(f"  {h['type']} {h['id']}")
            print(f"    {h['assertion']}")
            print(f"    {h['status']} · {h['assurance']} · "
                  f"{sup['attesting_count']} attesting — {state}\n")

    _emit(args, payload, render_list if (not args.id and not args.ask) else render_one)


def cmd_findings(args) -> None:
    """Claims and conjectures as hypotheses, not as node ids.

    With `--id`, the whole dossier for one of them: what is asserted, how it
    was reached, what was searched, what could have gone wrong in the
    selection, what else could explain the same evidence, the prediction
    recorded when it was proposed and what happened when it was run."""
    graph = _read(args)
    try:
        if args.id:
            payload = dossier_json(graph, args.id)
        else:
            payload = findings_json(graph, limit=args.limit)
    except NodeNotFound as e:
        raise SystemExit(str(e)) from e
    finally:
        graph.close()

    def render_list(p):
        if not p["findings"]:
            print("no claims or conjectures yet")
            return
        print(f"{p['count']} finding(s) — newest first, deliberately unranked\n")
        for f in p["findings"]:
            sup = f["support"]
            flag = (
                "nothing attests it yet" if sup["vacuous"]
                else "independent" if sup["independent"]
                else "SHARED DESCENT"
            )
            print(f"{f['id']}")
            print(f"  {f['assertion'] or '(no text)'}")
            marks = [f["status"], f["assurance"]]
            if f["has_dossier"]:
                marks.append("dossier")
            if f["prospective_result"]:
                marks.append(f"prospective:{f['prospective_result']}")
            elif f["has_prospective_query"]:
                marks.append("prospective:not run")
            print(f"  {' · '.join(marks)}")
            print(f"  {sup['attesting_count']} attesting, "
                  f"{sup['distinct_witnesses']} distinct witness(es) — {flag}")
            if f["rejected_reason"]:
                print(f"  rejected: {f['rejected_reason']}")
            print()

    def render_one(p):
        print(f"{p['id']}  {p['status']} · {p['assurance']}")
        print(f"\n{p['assertion'] or '(no text)'}\n")
        for field, value in p["dossier"].items():
            print(f"  {field.replace('_', ' ')}")
            print(f"    {value}")
        for q in p["prior_art"]:
            print(f"\n  prior art searched\n    {q['text']}")
        for q in p["prospective_queries"]:
            print(f"\n  prospective query\n    {q['text']!r}")
            if q["expectation"]:
                word = "at most" if q["expectation"] == "at_most" else "at least"
                print(f"    predicted {word} {q['expected_hits']}, recorded at proposal")
        t = p.get("prospective_test")
        if t:
            print(f"    -> {t['payload']['result'].upper()}: {t['payload']['detail']}")
        sup = p.get("independent_support")
        if sup:
            flag = (
                "nothing attests it yet" if sup["vacuous"]
                else "independent" if sup["independent"]
                else "SHARED DESCENT — discounted"
            )
            print(f"\n  support\n    {sup['attesting_count']} attesting, "
                  f"{sup['distinct_witnesses']} distinct witness(es) — {flag}")
        if p["evidence"]:
            print(f"\n  evidence ({len(p['evidence'])})")
            for e in p["evidence"]:
                print(f"    {e['canonical_ref']}  {e['assurance']}")
                print(f"      {e['excerpt']!r}")
        if p["latest_verifications"]:
            print("\n  verifications (latest per method)")
            for v in p["latest_verifications"]:
                vp = v["payload"]
                print(f"    {vp['method']}: {vp['result']}")
                print(f"      machine: {vp.get('detail')}")
                if vp.get("limitations"):
                    print(f"      limits:  {vp['limitations']}")

    _emit(args, payload, render_one if args.id else render_list)


def cmd_test_conjecture(args) -> None:
    """Re-run a conjecture's prospective query and compare it to the
    prediction recorded when the conjecture was proposed.

    A write, because it records a verification — so it takes the writer's lock
    like every other write, and answers the same way if a run holds it."""
    from .tools.run_prospective_test import run_prospective_test

    source = _corpus(args)
    try:
        graph = _write(args)
    except SingleWriterViolation as e:
        raise SystemExit(f"the graph is locked by another writer (an agent run?): {e}") from e
    try:
        report = run_prospective_test(
            graph, source, args.id, authored_by=RESEARCHER,
        )
        payload = report.model_dump(mode="json")
    except NodeNotFound as e:
        raise SystemExit(str(e)) from e
    except CohortError as e:
        raise SystemExit(f"refused ({type(e).__name__}): {e}") from e
    finally:
        graph.close()

    def render(p):
        print(f"{p['conjecture_id']}  {p['result']}")
        print(f"  query    {p['query_text']!r}  ({p['query_id']})")
        if p["expectation"] is None:
            print("  predicted  nothing was recorded")
        else:
            word = "at most" if p["expectation"] == "at_most" else "at least"
            print(f"  predicted  {word} {p['expected_hits']}")
        cap = " (the search cap — a floor, not a count)" if p["count_saturated"] else ""
        print(f"  observed   {p['observed_hits']}{cap}")
        print(f"  {p['note']}")
        print(f"  recorded as {p['verification_id']}")
    _emit(args, payload, render)


# --- corpus commands --------------------------------------------------------

def cmd_search(args) -> None:
    source = _corpus(args)
    hits = source.search(args.query, max_results=args.limit)
    payload = {
        "query": args.query, "count": len(hits),
        "ordering": "corpus order; no relevance ranking",
        "truncated": len(hits) >= args.limit,
        "hits": [h.model_dump(mode="json") for h in hits],
    }

    def render(p):
        for h in p["hits"]:
            print(f"{h['ref']}\n    {h.get('snippet', '')}")
        print(f"\n{p['count']} hit(s) — {p['ordering']}")
    _emit(args, payload, render)


def cmd_fetch(args) -> None:
    source = _corpus(args)
    record = source.fetch(args.ref)
    text = record.text[: args.max_chars]
    if args.strip_markup:
        from .sources.cbeta_markup import strip_markup_for_display
        text = strip_markup_for_display(text)
    payload = {
        "ref": args.ref, "witness_ref": record.witness_ref, "title": record.title,
        "locator": record.locator, "source_terms": record.note,
        "truncated": len(record.text) > args.max_chars, "text": text,
    }

    def render(p):
        print(f"{p['witness_ref']}  {p['title'] or ''}")
        # The licence rides with the text, here as everywhere else.
        if p.get("source_terms"):
            print(f"terms: {p['source_terms']}")
        print()
        print(p["text"])
        if p["truncated"]:
            print("\n… truncated; raise --max-chars for more")
    _emit(args, payload, render)


def cmd_context(args) -> None:
    """A passage in context — the terminal side of `/api/passage/context`,
    sharing `verified_span_for`/`locate_passage_span` (cohort/views.py) so the
    two cannot locate the same excerpt two different ways."""
    graph = _read(args)
    try:
        try:
            node = graph.get_node(args.id)
        except NodeNotFound as e:
            raise SystemExit(str(e)) from e
        if node.type != NodeType.PASSAGE:
            raise SystemExit(f"{args.id} is a {node.type}, not a passage")
        source_ref = node.payload.get("source_ref")
        excerpt = node.payload.get("excerpt")
        if not source_ref or not excerpt:
            raise SystemExit(
                f"{args.id} has no source_ref or no excerpt recorded, "
                "so there is nothing to re-fetch context from"
            )
        verified_span = verified_span_for(graph, args.id)
    finally:
        graph.close()

    source = _corpus(args)
    record = source.fetch(source_ref)
    try:
        start, end, location = locate_passage_span(record.text, excerpt, verified_span)
    except ValueError as e:
        raise SystemExit(str(e)) from e

    window = args.window
    payload = {
        "id": args.id,
        "before": record.text[max(0, start - window):start],
        "excerpt": record.text[start:end],
        "after": record.text[end:end + window],
        "has_more_before": start - window > 0,
        "has_more_after": end + window < len(record.text),
        "location": location,
        "window": window,
        "source_ref": source_ref,
        "witness_ref": record.witness_ref,
    }

    def render(p):
        more_before = "… " if p["has_more_before"] else ""
        more_after = " …" if p["has_more_after"] else ""
        print(f"{more_before}{p['before']}[{p['excerpt']}]{p['after']}{more_after}")
        print(f"\n{p['witness_ref']} · located by {p['location']}")
    _emit(args, payload, render)


# --- attribution evidence ---------------------------------------------------

def _attribution(args):
    from .attribution import AttributionIndex
    root = args.radich or os.environ.get("RADICH_ROOT", "data/radich")
    try:
        return AttributionIndex.load(root)
    except FileNotFoundError as e:
        raise SystemExit(f"no Radich data at {root}: {e}\n(pass --radich PATH or set RADICH_ROOT)") from e


def cmd_evidence(args) -> None:
    index = _attribution(args)
    if args.list:
        payload = index.units()

        def render_list(p):
            for row in p["units"]:
                flag = "  profiled" if row["profiled"] else ""
                print(f"{row['uid']:<40}{row['label']:<16}{row['han_chars']:>8}{flag}")
            print("\nledger")
            for k, v in p["ledger"].items():
                print(f"  {k:<58}{v:>7}")
            for n in p["notes"]:
                print(f"  note: {n}")
        _emit(args, payload, render_list)
        return
    if not args.uid:
        raise SystemExit("give a unit id (e.g. T0603), or --list")
    pinned = tuple(x.strip() for x in args.pair.split(",")) if args.pair else None
    if pinned is not None and len(pinned) != 2:
        raise SystemExit("--pair takes exactly two class labels, e.g. --pair ASg,pre-Dhr-other")
    try:
        payload = index.evidence(
            args.uid, args.features,
            withhold=[u.strip() for u in args.withhold.split(",") if u.strip()],
            offset=args.offset, pair=pinned,  # type: ignore[arg-type]
        )
    except (KeyError, ValueError) as e:
        raise SystemExit(str(e.args[0] if e.args else e)) from e

    def render(p):
        print(f"{p['uid']}  catalogue label: {p['label']}  "
              f"features: {p['features']} ({p['n_features']:,} strings)")
        print(f"{p['han_chars']:,} Han characters ({p['code_points']:,} code points), "
              f"{p['hits']:,} feature hits, {p['distinct']:,} distinct; "
              f"{p['withheld_units']} unit(s) withheld from the profiles"
              + (f" (incl. {', '.join(p['withheld_extra'])})" if p["withheld_extra"] else ""))
        if p["verdict"] == "no evidence":
            print("\nno evidence: not one string of this vocabulary occurs in the text. "
                  "Nothing is ranked.")
            return
        flag = "  (LOW EVIDENCE: fewer than 10 distinct strings)" if p["verdict"] == "low evidence" else ""
        print(f"\nleans {p['first']} over {p['second']}  "
              f"margin {p['margin']:+.2f} log-odds per distinct string{flag}")
        print("ranking: " + "  ".join(f"{r['label']} {r['delta']:+.0f}" for r in p["ranking"]))
        thin = [f"{lab} ({v['units']} of {v['units_before_withholding']} units left)"
                for lab, v in p["profiles"].items() if v["thin"]]
        if thin:
            print("thin profiles after withholding: " + "; ".join(thin))
        if p["no_profile"]:
            print("not judged: " + "; ".join(f"{n['label']} ({n['reason']})" for n in p["no_profile"]))
        a, b = p["pair"]["a"], p["pair"]["b"]
        print(f"\npainted pair: {a} (A) vs {b} (B); profiles hold "
              f"{p['profiles'][a]['feature_tokens']:,} and {p['profiles'][b]['feature_tokens']:,} feature tokens")
        w = max(len(a), len(b)) + 10
        for side, key in ((a, "for"), (b, "against")):
            print(f"\n  {'for ' + side:<20}{'hits':>6}{a + ' n /100k':>{w}}{b + ' n /100k':>{w}}{'weight':>8}")
            for r in p[key]:
                print(f"  {r['gram']:<20}{r['hits']:>6}"
                      f"{str(r['count_a']) + ' ' + format(r['rate_a'], '.1f'):>{w}}"
                      f"{str(r['count_b']) + ' ' + format(r['rate_b'], '.1f'):>{w}}{r['weight']:>+8.1f}")
        print("\nRates are per 100,000 feature tokens in that profile (n = raw count), not per "
              "100,000 characters.\nA leaning, not an attribution: the researcher reads the strings above.")
    _emit(args, payload, render)


# --- agent runs -------------------------------------------------------------

def cmd_run(args) -> None:
    """Start a run and wait for it. The web launcher is asynchronous because a
    browser cannot block; a terminal can, so this stays in the foreground and
    Ctrl-C is the stop button."""
    from .ui.runs import ROLE_REVIEWER, AgentSpec, RunManager, RunRejected

    if args.history:
        _run_history(args)
        return

    source = _corpus(args)
    workers = args.agent or []
    reviewers = args.reviewer or []

    # `--question` with no roster plans one. Same function the browser's auto
    # mode calls, deliberately: the parity this project promises is not that
    # both front ends can start a run, it is that a run started either way is
    # the same run.
    if args.question and not workers and not reviewers:
        from .agents.openrouter import load_model_pool
        from .graph import Graph
        from .ui.runs import plan_inquiry

        with Graph.open_read_only(Path(args.db)) as g:
            payload = g.get_node(args.question).payload or {}
        specs = plan_inquiry(
            str(payload.get("text") or ""),
            answerable_by=str(payload.get("answerable_by") or ""),
            models=load_model_pool(), max_agents=args.max_agents,
        )
        print(f"planned {len(specs)} agent(s) for {args.question}:")
        for spec in specs:
            print(f"  {spec.agent_id}  {spec.role}  {spec.method_label}  "
                  f"{spec.model or '(default model)'}")
        print()
    elif not workers and not reviewers:
        raise SystemExit(
            "give at least one --agent or --reviewer, or --question ID to have "
            "the roster planned."
        )
    else:
        specs = None

    def paired(instructions: list[str], models: list[str], flag: str) -> list[str]:
        """One model per instruction, or none at all. A partial list is
        refused rather than padded: silently defaulting the rest is how two
        agents end up on one family, which the run would then refuse anyway
        with a message about a roster the caller did not write."""
        if models and len(models) != len(instructions):
            raise SystemExit(
                f"{len(instructions)} {flag} but {len(models)} {flag}-model: give "
                f"one model per {flag}, or none and they all use the configured "
                "default (which a run of more than one agent will then refuse, "
                "since no two agents in a run may share a model family)."
            )
        return models or [""] * len(instructions)

    worker_models = paired(workers, args.model or [], "--agent")
    reviewer_models = paired(reviewers, args.reviewer_model or [], "--reviewer")

    def declared(values: list[str] | None, flag: str) -> list[str]:
        """One declared commitment per agent, in roster order (--agent first,
        then --reviewer), or one shared by all of them.

        Distinct declared scope per agent is the design's own condition for
        allowing more than one agent at all (docs/roadmap.md "Scope revision"),
        and `POST /api/run` has always taken these per agent — a terminal that
        could only set them for the whole roster could not say what the web
        launcher could. A single shared value stays legal: two agents may
        divide one corpus by method rather than by scope."""
        values = values or []
        total = len(workers) + len(reviewers)
        if not values:
            return [""] * total
        if len(values) == 1:
            return list(values) * total
        if len(values) != total:
            raise SystemExit(
                f"{total} agent(s) but {len(values)} {flag}: give one per agent "
                "in roster order (--agent first, then --reviewer), one for all "
                "of them, or none at all."
            )
        return list(values)

    scopes = declared(args.scope, "--scope")
    methods = declared(args.method, "--method")

    if specs is None:
        specs = [
            AgentSpec(agent_id=f"agent:cli-{i + 1}", instructions=text,
                      corpus_scope=scopes[i], method_label=methods[i],
                      model=worker_models[i])
            for i, text in enumerate(workers)
        ]
        # Reviewers come after the workers in the roster because that is the
        # order they run in: a reviewer starting alongside the workers would
        # have nothing proposed yet to review (`RunManager._execute`).
        specs += [
            AgentSpec(agent_id=f"agent:cli-reviewer-{i + 1}", instructions=text,
                      corpus_scope=scopes[len(workers) + i],
                      method_label=methods[len(workers) + i],
                      model=reviewer_models[i], role=ROLE_REVIEWER)
            for i, text in enumerate(reviewers)
        ]
    manager = RunManager(
        Path(args.db), _log_path(args), source,
        max_budget_usd=args.budget, max_turns=args.max_turns,
    )
    try:
        manager.start(specs, budget_usd=args.budget, max_turns=args.max_turns,
                      question_id=args.question)
    except RunRejected as e:
        raise SystemExit(f"refused: {e}") from e

    async def wait() -> dict[str, Any] | None:
        """Poll the same way the browser does — `current()`/`history()` are the
        run manager's whole status surface, and `GET /api/run` is these two."""
        while True:
            current = manager.current()
            if not current or current["state"] not in ("starting", "running"):
                return current
            await asyncio.sleep(0.5)

    try:
        run = asyncio.run(wait())
    except KeyboardInterrupt:
        manager.stop()
        raise SystemExit("\nstopping after this turn…") from None

    if run is None:
        history = manager.history(limit=1)
        run = history[0] if history else {}

    def render(p):
        r = p
        spend = r.get("spend", {})
        print(f"{r.get('state')}  {r.get('elapsed_s')}s  "
              f"${spend.get('spent_usd', 0):.5f} of ${spend.get('budget_usd', 0):.2f}"
              f"  {spend.get('calls', 0)} call(s)")
        for a in r.get("agents", []):
            print(f"\n{a['agent_id']}")
            if a.get("error"):
                print(f"  error: {a['error']}")
            for c in a.get("tool_calls", []):
                mark = "refused" if c.get("is_error") else "ok"
                print(f"  [{mark}] {c['tool']}: {str(c.get('result'))[:120]}")
        if r.get("error"):
            print(f"\nrun error: {r['error']}")
    _emit(args, run, render)


def _run_history(args) -> None:
    """Past runs, read from the log rather than from a run manager.

    Needs no corpus, no key and no run manager: a run is a pair of events, so
    this answers "what has been run against this graph" long after every
    process that ran one has exited."""
    log = _log_path(args)
    runs = read_runs(log, limit=args.limit_runs)
    payload = {"log_path": str(log), "runs": [r.model_dump(mode="json") for r in runs]}

    def render(p):
        if not p["runs"]:
            print(f"no runs recorded in {p['log_path']}")
            return
        for r in p["runs"]:
            spent = f"${r['spent_usd']:.5f}" if r["spent_usd"] is not None else "—"
            state = r["state"] or "open"
            print(f"{r['run_id']}  {state:<9} {r['started_at']}  {spent}  "
                  f"{r['calls']} call(s)  {r['events']} event(s)  "
                  f"{r['refusals']} refused")
            for a in r["agents"]:
                scope = a.get("corpus_scope") or "no declared scope"
                print(f"    {a['role']:<8} {a['agent_id']:<22} {a.get('model') or '—'}"
                      f"  — {scope}")
            if r["error"]:
                print(f"    error: {r['error']}")
    _emit(args, payload, render)


# --- parser -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cohort",
        description="COHORT from the terminal — the same capabilities as the web UI.",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"graph projection (default {DEFAULT_DB})")
    parser.add_argument("--log", default=None, help="event log (default: --db with .jsonl)")
    parser.add_argument("--json", action="store_true", help="print the API's own JSON shape")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=fn)
        return p

    add("health", cmd_health, "node and edge counts")

    p = add("graph", cmd_graph, "list nodes and the edges between them")
    p.add_argument("--type", choices=[t.value for t in NodeType])
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--include-retracted", action="store_true",
                   help="also show edges the researcher has withdrawn")

    p = add("node", cmd_node, "one node with its full provenance")
    p.add_argument("id")

    add("citable", cmd_citable, "accepted nodes — the only ones citable by output")

    p = add("rejected", cmd_rejected, "rejected nodes, with their reasons")
    p.add_argument("--type", choices=[t.value for t in NodeType])

    p = add("agent", cmd_agent, "an agent's contribution counts")
    p.add_argument("id")

    p = add("refusals", cmd_refusals, "writes the graph refused, and which rule refused them")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--census", action="store_true",
                   help="the summary only, without the individual refusals: counts by "
                        "rule and category, and streaks of one agent refused repeatedly "
                        "by one rule. The census always covers the whole log, never the "
                        "--limit tail")
    p.add_argument("--run", default=None, metavar="RUN_ID",
                   help="narrow to one agent run (see `cohort run --history`). The "
                        "log is cumulative across a graph's whole life, so this is a "
                        "different question from what the graph has ever refused")

    p = add("question", cmd_question,
            "research questions — what an inquiry was asking")
    p.add_argument("--id", default=None, help="read one, with what addresses it")
    p.add_argument("--ask", default=None, metavar="TEXT",
                   help="record a new research question (researcher only)")
    p.add_argument("--answerable-by", default="", metavar="TEXT",
                   help="what would count as an answer — required with --ask, and "
                        "stated before looking so the question cannot be quietly "
                        "reshaped to fit whatever turned up")
    p.add_argument("--address", default=None, metavar="NODE_ID",
                   help="record that this claim or conjecture answers --id")

    p = add("findings", cmd_findings,
            "claims and conjectures as hypotheses, with their dossiers")
    p.add_argument("--id", default=None, help="the full dossier for one of them")
    p.add_argument("--limit", type=int, default=None)

    p = add("test-conjecture", cmd_test_conjecture,
            "re-run a conjecture's prospective query against its recorded prediction")
    p.add_argument("id", help="the conjecture id")

    p = add("integrity", cmd_integrity, "re-hash stored payloads against their recorded hashes")
    p.add_argument("--id", default=None, help="check one node instead of all")

    add("rebuild", cmd_rebuild, "replay the log and diff it against this projection")

    p = add("attest", cmd_attest,
            "run the mechanical check: do this node's citations resolve? "
            "As the researcher, who is exempt from the rule that an agent may "
            "not attest what it authored — so this is the way through when a "
            "run left its claims at proposed with no reviewer")
    p.add_argument("id")

    p = add("accept", cmd_accept, "promote a node to accepted (as the researcher)")
    p.add_argument("id")

    p = add("reject", cmd_reject, "reject a node, with a reason (as the researcher)")
    p.add_argument("id")
    p.add_argument("--reason", required=True)

    p = add("reopen", cmd_reopen, "reopen a rejected node (as the researcher)")
    p.add_argument("id")
    p.add_argument("--reason", required=True)

    p = add("retract-edge", cmd_retract_edge,
            "withdraw an edge, with a reason (as the researcher)")
    p.add_argument("id")
    p.add_argument("--reason", required=True)

    p = add("restore-edge", cmd_restore_edge,
            "undo a retraction, with a reason (as the researcher)")
    p.add_argument("id")
    p.add_argument("--reason", required=True)

    p = add("search", cmd_search, "search the corpus")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    p = add("fetch", cmd_fetch, "fetch one corpus record")
    p.add_argument("ref")
    p.add_argument("--max-chars", type=int, default=8000)
    p.add_argument("--strip-markup", action="store_true",
                   help="display only — this breaks offsets, so never store the result")

    p = add("context", cmd_context,
            "a passage in context: chars of source text on each side of its recorded excerpt")
    p.add_argument("id", help="a passage node id")
    p.add_argument("--window", type=int, default=10,
                   help="characters of context on each side (default 10)")

    p = add("evidence", cmd_evidence,
            "where one text leans between translator profiles, and the strings that make it lean")
    p.add_argument("uid", nargs="?", help="a unit id from Radich's catalogue, e.g. T0603")
    p.add_argument("--features", choices=list(FEATURE_SETS), default="radich",
                   help="his curated strings, the corpus's commonest strings, or both")
    p.add_argument("--list", action="store_true",
                   help="every unit with a base text, and the ledger of what was discarded")
    p.add_argument("--withhold", default="", metavar="UNITS",
                   help="comma-separated profiled unit ids to withhold as well (the sensitivity test)")
    p.add_argument("--pair", default="", metavar="A,B",
                   help="paint A vs B instead of the catalogue label vs its strongest rival")
    p.add_argument("--offset", type=int, default=0, help="first character of the painted excerpt")
    p.add_argument("--radich", default=None,
                   help="the Radich data folder (default: $RADICH_ROOT, else data/radich)")

    p = add("run", cmd_run, "run one or more agents against the graph (spends money)")
    p.add_argument("--agent", action="append", metavar="INSTRUCTIONS",
                   help="repeat for several agents")
    p.add_argument("--model", action="append", metavar="MODEL",
                   help="one per --agent; agents in a run may not share a model family")
    p.add_argument("--reviewer", action="append", metavar="INSTRUCTIONS",
                   help="a reviewer: checks claims the workers proposed and cannot "
                        "propose any of its own. Runs after them, since there is "
                        "nothing to review before. An agent may not attest a claim "
                        "it authored, so a run of workers alone leaves its claims "
                        "at proposed for a reviewer or for you to accept")
    p.add_argument("--reviewer-model", action="append", metavar="MODEL",
                   help="one per --reviewer; must be a different provider from the "
                        "workers it reviews, or the write is refused")
    p.add_argument("--scope", action="append", metavar="SCOPE",
                   help="declared corpus scope: one per agent in roster order, "
                        "or one for all of them")
    p.add_argument("--method", action="append", metavar="METHOD",
                   help="declared method, paired like --scope")
    p.add_argument("--question", metavar="ID",
                   help="the question node this run is answering. On its own, "
                        "with no --agent/--reviewer, the roster is planned for "
                        "it; alongside an explicit roster it just records what "
                        "the run was asked. Every claim or conjecture the run "
                        "proposes gets an `addresses` edge to it")
    p.add_argument("--budget", type=float, default=0.25, help="hard USD cap for the run")
    p.add_argument("--max-turns", type=int, default=8)
    p.add_argument("--max-agents", type=int, default=4,
                   help="ceiling on a planned roster (--question). An explicit "
                        "roster is bounded by what you pass, not by this")
    p.add_argument("--history", action="store_true",
                   help="list past runs from the event log instead of starting one. "
                        "Spends nothing and needs no corpus or key")
    p.add_argument("--limit-runs", type=int, default=20, metavar="N",
                   help="how many past runs --history lists")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
