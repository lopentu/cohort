"""Read-only JSON API over the evidence graph (build order stage 5).

**Reads never take the writer lock.** Every read endpoint opens the
projection through `Graph.open_read_only()`, which takes no lock and cannot
write (SQLite `mode=ro`, no `EventLog` attached), so the API keeps serving
while an agent run is writing.

**Writes are opt-in, and hold the lock for one request only.** The
researcher's accept/reject (docs/design.md §13 stage 5) lives here now, behind
`allow_writes`. An earlier version of this docstring argued a writing UI
would have to hold the exclusive lock "for as long as a browser tab is
open" — that was never actually required. Each write endpoint calls
`Graph.open()` for the duration of one request and closes it, so the lock is
held for milliseconds, not for a session. Single-writer discipline is
therefore unchanged, not relaxed: if an agent run holds the lock, `flock`
refuses, and the endpoint answers `409 Conflict` saying so, rather than
queueing, retrying, or (worst) weakening the lock.

Writes default to **off** so the read-only deployment stays the default, and
because these endpoints act as `RESEARCHER` — the one identity the promotion
ladder treats as privileged (docs/design.md §8, "Only the researcher"). Enabling
them is the operator asserting that whoever can reach this port *is* the
researcher, which is a claim only the operator can make.

**What the API must not flatten.** docs/design.md §10 warns that a naive
projection of this graph into a knowledge graph "flattens exactly the
epistemics that justify the system": if the view shows nodes without status
and edges without the independence flag, it silently restores the consensus
illusion, because a densely-linked node then looks well-supported regardless
of whether its support is independent. So `/graph` returns node `status` and
edge `type` on every element rather than leaving the frontend to fetch them,
and `discounts` marks the edge types (`descends_from`, `parallel_of`) that
*reduce* support instead of adding it. The frontend is then able to render the
distinction — this layer at least makes it impossible to omit by accident.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..errors import (
    CohortError,
    EdgeNotFound,
    NodeNotFound,
    RebuildMismatch,
    SingleWriterViolation,
)
from ..eventlog import read_refusals, summarize_refusals
from ..graph import Graph
from pydantic import ValidationError

from ..schemas import RESEARCHER, EdgeType, NodeType, QuestionPayload
from ..sources.base import Source
from ..sources.cbeta_markup import strip_markup_for_display
from ..sources.cbeta_refs import reader_url
from ..views import (
    DISCOUNTING_EDGE_TYPES,
    dossier_json,
    findings_json,
    node_detail_json,
    question_json,
    questions_json,
)
from ..views import edge_json as _edge_json
from ..views import node_json as _node_json
from .runs import ROLE_WORKER, AgentSpec, RunManager, RunRejected, plan_inquiry

FRONTEND_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    db_path: str | Path,
    log_path: str | Path | None = None,
    *,
    allow_writes: bool = False,
    source: Source | None = None,
    run_manager: RunManager | None = None,
) -> FastAPI:
    """Build the app around one projection path.

    A fresh read-only `Graph` is opened per request rather than held open for
    the app's lifetime. That is deliberate: an agent run writing to the same
    file advances it constantly, and a long-lived connection would serve a
    snapshot that silently ages. It also keeps sqlite3's same-thread rule
    satisfied without pinning the server to one worker.

    `log_path` defaults to `db_path` with a `.jsonl` suffix, the convention
    every script already uses. It is needed for `/api/refusals`, which reads
    the event log directly: a refused write changed no graph state, so there
    is nothing in the SQLite projection to read it from.

    `allow_writes` mounts the researcher's accept/reject endpoints. Off by
    default — see this module's docstring.

    `source` mounts the corpus browse/search endpoints. It is a *reader*, so
    these are ordinary read endpoints and take no lock. They exist because the
    Python API can search the corpus and the web UI could not, and the point
    of this layer is parity.

    `run_manager` mounts the agent-run endpoints — the one part of the API that
    can spend money. Off unless passed; see `cohort/ui/runs.py`."""
    db_path = Path(db_path)
    log_path = Path(log_path) if log_path is not None else db_path.with_suffix(".jsonl")
    app = FastAPI(
        title="COHORT",
        summary="Read-only view of the evidence graph.",
        version="0.1.0",
    )

    def read() -> Graph:
        try:
            return Graph.open_read_only(db_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        graph = read()
        try:
            counts: dict[str, int] = {}
            for row in graph.conn.execute("SELECT type, COUNT(*) c FROM nodes GROUP BY type"):
                counts[row["type"]] = row["c"]
            edges = graph.conn.execute("SELECT COUNT(*) c FROM edges").fetchone()["c"]
            return {
                "ok": True, "db_path": str(db_path), "nodes": counts, "edges": edges,
                "writes_enabled": allow_writes,
                "corpus_enabled": source is not None,
                "runs_enabled": run_manager is not None,
            }
        finally:
            graph.close()

    @app.get("/api/graph")
    def graph_view(
        node_type: NodeType | None = Query(default=None),
        limit: int = Query(default=500, ge=1, le=5000),
    ) -> dict[str, Any]:
        """Nodes and edges for the graph view.

        `truncated` is reported explicitly: a silently cut graph would show
        fewer supporting witnesses than exist, which in this system is not a
        cosmetic omission — it changes what the picture appears to say about
        support."""
        graph = read()
        try:
            # fetch one extra to detect truncation without a second COUNT query
            nodes = graph.nodes(node_type=node_type, limit=limit + 1)
            truncated = len(nodes) > limit
            nodes = nodes[:limit]
            ids = {n.id for n in nodes}
            edges = [e for e in graph.edges() if e.src in ids and e.dst in ids]
            return {
                "nodes": [_node_json(graph, n) for n in nodes],
                "edges": [_edge_json(e) for e in edges],
                "truncated": truncated,
                "discounting_edge_types": sorted(DISCOUNTING_EDGE_TYPES),
            }
        finally:
            graph.close()

    @app.get("/api/node")
    def node_detail(id: str = Query(..., min_length=1)) -> dict[str, Any]:
        """One node with everything needed for provenance on click: its
        payload and authorship, its verifications, its edges in both
        directions, and — for a claim or conjecture — the independence of its
        support.

        The id is a **query parameter, not a path segment**, because node ids
        are opaque and routinely contain `#`: a passage's canonical ref is
        `{witness}#{excerpt}`. In a path, `#` starts the fragment and never
        reaches the server, so `/api/nodes/passage:T08n0250#...` silently
        arrives as a request for `passage:T08n0250` and 404s. A query
        parameter is the ordinary place for an opaque value, and every URL
        builder percent-encodes it correctly."""
        node_id = id
        graph = read()
        try:
            try:
                graph.get_node(node_id)
            except NodeNotFound as e:
                raise HTTPException(status_code=404, detail=str(e)) from e

            return node_detail_json(graph, node_id)
        finally:
            graph.close()

    @app.get("/api/citable")
    def citable() -> list[dict[str, Any]]:
        graph = read()
        try:
            return [_node_json(graph, n) for n in graph.citable()]
        finally:
            graph.close()

    @app.get("/api/rejected")
    def rejected(node_type: NodeType | None = Query(default=None)) -> list[dict[str, Any]]:
        graph = read()
        try:
            return [_node_json(graph, n) for n in graph.rejected(node_type=node_type)]
        finally:
            graph.close()

    @app.get("/api/agent")
    def agent_report(id: str = Query(..., min_length=1)) -> dict[str, Any]:
        """Query parameter for the same reason as `/api/node`: agent ids are
        opaque strings (`agent:worker-heart`) and must survive encoding."""
        agent_id = id
        graph = read()
        try:
            report = graph.agent_report(agent_id).model_dump(mode="json")
            profile = graph.agent_profile(agent_id)
            report["profile"] = profile.model_dump(mode="json") if profile else None
            return report
        finally:
            graph.close()

    @app.get("/api/refusals")
    def refusals(
        limit: int = Query(default=100, ge=1, le=1000),
        run_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The refused writes, most recent last.

        This is an output surface, not a debug view: docs/design.md §15 claims the
        system's "refusals are part of its scholarly output", and until this
        endpoint existed they were visible only in `demo.py`'s terminal
        printout. Read from the event log rather than the projection —
        a refusal changed no state, so there is no row for it.

        A missing log is not an error: an in-memory or freshly copied
        projection can legitimately have none, and reporting `available:
        false` says that honestly instead of implying zero refusals.

        `census` summarises the **whole** log even when `refusals` is a
        truncated tail — a census of the tail would report a smaller total
        than the log holds while looking authoritative. See `RefusalCensus`.

        `run_id` narrows both to one agent run. The log is cumulative across a
        graph's whole life, so "what did the run I just watched refuse?" and
        "what has this graph ever refused" are different questions."""
        if not log_path.is_file():
            return {
                "available": False, "log_path": str(log_path), "refusals": [],
                "total": 0, "census": None,
            }
        all_refusals = read_refusals(log_path, run_id=run_id)
        shown = all_refusals[-limit:]
        return {
            "available": True,
            "log_path": str(log_path),
            "run_id": run_id,
            "total": len(all_refusals),
            "truncated": len(shown) < len(all_refusals),
            "refusals": [r.model_dump(mode="json") for r in shown],
            "census": summarize_refusals(log_path, run_id=run_id).model_dump(mode="json"),
        }

    @app.get("/api/questions")
    def questions(id: str | None = Query(default=None)) -> dict[str, Any]:
        """Research questions. With `id`, one of them and what addresses it.

        A COHORT graph used to record what was found and never what was being
        asked, so a findings page had no title it could honestly give itself
        and an agent's declared scope was a scope of nothing in particular.

        The per-question view is a **tally, not a verdict**: it says how many
        hypotheses address the question and where each stands, never whether
        the question is answered. Nothing mechanical could know that."""
        graph = read()
        try:
            if id is not None:
                try:
                    return question_json(graph, id)
                except NodeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
            return questions_json(graph)
        finally:
            graph.close()

    @app.get("/api/findings")
    def findings(
        id: str | None = Query(default=None),
        limit: int | None = Query(default=None, ge=1, le=1000),
    ) -> dict[str, Any]:
        """Claims and conjectures as hypotheses rather than as node ids.

        Without `id`, the scannable list; with it, the whole dossier — the
        assertion, how it was reached, what was searched, what could have gone
        wrong in the selection, what else could explain the same evidence, the
        prediction recorded when it was proposed, and what happened when it was
        run. All of it was already in the graph and reachable only by walking
        edges by hand, which is the step at which the honest fields get
        skipped.

        Deliberately unranked. A list sorted by "most attested" would be a
        confidence ranking wearing a different hat."""
        graph = read()
        try:
            if id is not None:
                try:
                    return dossier_json(graph, id)
                except NodeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
            return findings_json(graph, limit=limit)
        finally:
            graph.close()

    @app.get("/api/integrity")
    def integrity(id: str | None = Query(default=None)) -> dict[str, Any]:
        """Re-hash stored payloads and compare against their recorded hashes.

        A read, not a repair: it reports tampering rather than correcting it,
        and it is on demand rather than ambient because one bad row must not
        turn every future read touching it into a crash."""
        graph = read()
        try:
            return graph.verify_integrity(id).model_dump(mode="json")
        finally:
            graph.close()

    @app.get("/api/rebuild")
    def rebuild() -> dict[str, Any]:
        """Replay the event log into a shadow graph and diff it against this
        projection — the check that the log, not the database, is ground truth
        (docs/design.md §5 principle 1).

        A mismatch is this endpoint's most important answer, so it is reported
        as `ok: false` with the diff rather than raised as a 500: the projection
        being wrong is a finding about the system, not a fault in the request.

        GET because it changes nothing. `rebuild` names what it replays into a
        throwaway in-memory graph, not anything it writes here."""
        if not log_path.is_file():
            return {"available": False, "log_path": str(log_path)}
        graph = read()
        try:
            report = graph.rebuild(log_path=log_path).model_dump(mode="json")
            return {"available": True, "log_path": str(log_path), **report}
        except RebuildMismatch as e:
            return {
                "available": True, "log_path": str(log_path),
                "ok": False, "mismatch": str(e),
            }
        finally:
            graph.close()

    if allow_writes:

        def _write_graph() -> Graph:
            """Open the graph for writing for the length of one request.

            `Graph.open()` takes a non-blocking exclusive `flock`. If an agent
            run holds it, that raises `SingleWriterViolation`, which becomes a
            409 rather than a 500: the researcher is told a run is in progress
            and can retry, which is true and actionable. Deliberately no
            retry loop and no lock timeout — a UI that silently waited on the
            lock would make the single-writer rule feel like a bug instead of
            a design commitment."""
            try:
                return Graph.open(db_path, log_path)
            except SingleWriterViolation as e:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{e} — an agent run is writing to this graph right now. "
                        "Nothing was changed; try again when it finishes."
                    ),
                ) from e
            except FileNotFoundError as e:
                raise HTTPException(status_code=503, detail=str(e)) from e

        def _verdict(node_id: str, action: str, reason: str | None) -> dict[str, Any]:
            graph = _write_graph()
            try:
                try:
                    method = {
                        "accept": graph.accept, "reject": graph.reject, "reopen": graph.reopen,
                    }[action]
                    kwargs: dict[str, Any] = {"authored_by": RESEARCHER}
                    if action in ("reject", "reopen"):
                        kwargs["reason"] = reason
                    decision_id = method(node_id, **kwargs)
                except NodeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
                except CohortError as e:
                    # A refused write, already recorded to the log by
                    # `graph._refuse()`. 422: the request was well formed but
                    # the graph's own rules declined it — which is a real
                    # answer from this system, not a server fault.
                    raise HTTPException(
                        status_code=422,
                        detail={"rule": type(e).__name__, "message": str(e)},
                    ) from e
                node = graph.get_node(node_id)
                return {
                    "node": _node_json(graph, node),
                    "decision_node_id": decision_id,
                }
            finally:
                graph.close()

        @app.post("/api/edge/retract")
        def retract_edge(
            id: str = Query(..., min_length=1),
            body: dict[str, Any] = Body(default={}),
        ) -> dict[str, Any]:
            """Withdraw an edge, with a reason. A researcher action.

            The edge that most needs this is `parallel_of`: a wrong one does
            not add noise, it *suppresses* independent support that really
            exists — silently, and in the direction of this system's own
            thesis. Nothing is deleted; the edge stays in the log and in the
            graph, marked withdrawn, and stops counting."""
            return _edge_verdict(id, "retract", (body or {}).get("reason"))

        @app.post("/api/edge/restore")
        def restore_edge(
            id: str = Query(..., min_length=1),
            body: dict[str, Any] = Body(default={}),
        ) -> dict[str, Any]:
            """Undo a retraction, with a reason. Without it, retraction would
            replace one irreversible mistake with another."""
            return _edge_verdict(id, "restore", (body or {}).get("reason"))

        @app.post("/api/attest")
        def attest(
            id: str = Query(..., min_length=1),
            body: dict[str, Any] = Body(default={}),
        ) -> dict[str, Any]:
            """Run the mechanical check and record it if it passes.

            Not a judgement, and not the researcher's signature: `attested`
            means the citations resolve, which is why docs/design.md §8 lets
            agents do it. The graph re-checks the precondition and refuses with
            a stated rule if the node has nothing attesting it, so this button
            cannot promote something unsupported.

            It exists because a node can be left eligible but unadvanced, and
            since 2026-09-02 that is the *ordinary* outcome rather than an
            agent stopping short: no agent may attest a claim it authored, so a
            run without a reviewer leaves its claims at `proposed`, where
            accept is correctly refused for skipping a rung. This is the
            researcher's way through — and the researcher is exempt from the
            author-is-not-reviewer rule, being the accountable party (see
            `Graph._reviewer_conflict`). The other way through is to add a
            reviewer on another provider to the run."""
            graph = _write_graph()
            try:
                try:
                    graph.attest(id, authored_by=RESEARCHER)
                except NodeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
                except CohortError as e:
                    raise HTTPException(
                        status_code=422,
                        detail={"rule": type(e).__name__, "message": str(e)},
                    ) from e
                return {"node": _node_json(graph, graph.get_node(id)), "decision_node_id": None}
            finally:
                graph.close()

        @app.post("/api/questions")
        def ask(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
            """Ask a research question, or record that a hypothesis answers one.

            `{text, answerable_by}` asks; `{id, address}` links a claim or
            conjecture to an existing question. Both act as `RESEARCHER` —
            setting the agenda is the supervision, and an agent that could ask
            its own question and then answer it would be doing unsupervised
            research with a paper trail."""
            graph = _write_graph()
            try:
                try:
                    if body.get("address"):
                        graph.add_edge(
                            EdgeType.ADDRESSES, str(body["address"]),
                            str(body.get("id") or ""), authored_by=RESEARCHER,
                        )
                        return question_json(graph, str(body.get("id") or ""))
                    qid = graph.ask_question(
                        QuestionPayload(
                            text=str(body.get("text") or ""),
                            answerable_by=str(body.get("answerable_by") or ""),
                        ),
                        authored_by=RESEARCHER,
                    )
                    return question_json(graph, qid)
                except NodeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
                except CohortError as e:
                    raise HTTPException(
                        status_code=422,
                        detail={"rule": type(e).__name__, "message": str(e)},
                    ) from e
                except ValidationError as e:
                    raise HTTPException(status_code=422, detail=str(e)) from e
            finally:
                graph.close()

        @app.post("/api/test-conjecture")
        def test_conjecture(id: str = Query(..., min_length=1)) -> dict[str, Any]:
            """Re-run a conjecture's prospective query and record the outcome.

            The falsifiability gate has always demanded a query that would
            settle a conjecture going forward, and until 2026-09-02 nothing
            ever ran it. This does — mechanically: a stored query re-run
            against the corpus, a stored integer compared to the count that
            comes back. No opinion enters, which is why it can be a
            `VerificationMethod` when `MODEL_ENTAILMENT` cannot.

            Behind `--allow-writes` because it records a verification, and
            behind a configured corpus because it has to search one."""
            from ..tools.run_prospective_test import run_prospective_test

            if source is None:
                raise HTTPException(
                    status_code=409,
                    detail="no corpus is configured, so the query cannot be run",
                )
            graph = _write_graph()
            try:
                try:
                    report = run_prospective_test(
                        graph, source, id, authored_by=RESEARCHER,
                    )
                except NodeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
                except CohortError as e:
                    raise HTTPException(
                        status_code=422,
                        detail={"rule": type(e).__name__, "message": str(e)},
                    ) from e
                return report.model_dump(mode="json")
            finally:
                graph.close()

        def _edge_verdict(edge_id: str, action: str, reason: str | None) -> dict[str, Any]:
            graph = _write_graph()
            try:
                method = graph.retract_edge if action == "retract" else graph.restore_edge
                try:
                    method(edge_id, authored_by=RESEARCHER, reason=reason or "")
                except EdgeNotFound as e:
                    raise HTTPException(status_code=404, detail=str(e)) from e
                except CohortError as e:
                    raise HTTPException(
                        status_code=422,
                        detail={"rule": type(e).__name__, "message": str(e)},
                    ) from e
                edge = next(
                    e for e in graph.edges(include_retracted=True) if e.id == edge_id
                )
                return {"edge": _edge_json(edge)}
            finally:
                graph.close()

        @app.post("/api/accept")
        def accept(
            id: str = Query(..., min_length=1),
            body: dict[str, Any] = Body(default={}),
        ) -> dict[str, Any]:
            """Promote a node to `accepted` as the researcher.

            Query parameter for the id, same reason as `/api/node`: passage
            ids contain `#`."""
            return _verdict(id, "accept", None)

        @app.post("/api/reject")
        def reject(
            id: str = Query(..., min_length=1),
            body: dict[str, Any] = Body(default={}),
        ) -> dict[str, Any]:
            """Reject a node, with a reason.

            The reason is required by the graph, not by this layer
            (`MissingRejectionReason`) — passing it through and letting the
            write boundary refuse keeps one rule in one place, and the refusal
            gets logged like any other."""
            return _verdict(id, "reject", (body or {}).get("reason"))

        @app.post("/api/reopen")
        def reopen(
            id: str = Query(..., min_length=1),
            body: dict[str, Any] = Body(default={}),
        ) -> dict[str, Any]:
            """Reopen a rejected node. A researcher action by design: docs/design.md
            §8 says rejection persists and "reopening is a researcher
            action"."""
            return _verdict(id, "reopen", (body or {}).get("reason"))

    # --- corpus (read-only; parity with CbetaReader in Python) ---------------

    if source is not None:

        @app.get("/api/corpus/search")
        def corpus_search(
            q: str = Query(..., min_length=1),
            limit: int = Query(default=20, ge=1, le=100),
        ) -> dict[str, Any]:
            """Search the corpus. Exactly `source.search()`, which is what a
            script calls, so a query typed here and a query typed in Python
            return the same hits in the same order.

            No relevance ranking, deliberately (see docs/handoff.md): results come
            back in corpus order, and saying so matters more than hiding it —
            a list that looks ranked but is not would misrepresent which
            witnesses are most relevant."""
            try:
                hits = source.search(q, max_results=limit)
            except NotImplementedError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"this corpus reader has no search index: {e}",
                ) from e
            return {
                "query": q,
                "count": len(hits),
                "ordering": "corpus order; no relevance ranking",
                "truncated": len(hits) >= limit,
                # A link to the published edition beside each hit. Provenance
                # for the reader, never for a check: `verify_exact_span`
                # re-fetches from the local archive whose bytes were hashed,
                # because a verification that depended on a remote page would
                # fail on a network error and pass or fail differently
                # depending on when it ran.
                "hits": [
                    {**h.model_dump(mode="json"), "cbeta_url": reader_url(h.ref)}
                    for h in hits
                ],
            }

        @app.get("/api/corpus/fetch")
        def corpus_fetch(
            ref: str = Query(..., min_length=1),
            # No meaningful floor: real records can be shorter than any
            # threshold worth naming (a four-line Tang poem is 26 characters),
            # and the caller controls the window it wants.
            max_chars: int = Query(default=8000, ge=1, le=200_000),
            strip_markup: bool = Query(default=False),
        ) -> dict[str, Any]:
            """Fetch one record. `ref` is a query parameter for the same
            reason node ids are: a CBETA ref is `entry_path::excerpt` and the
            excerpt is corpus text, which can contain anything.

            Truncated by default and **said so explicitly** in the response: a
            silently cut text would let a reader believe they had seen a whole
            witness. `source_terms` travels with every record, because the
            corpus is licensed (CC BY-NC-SA-equivalent) and its terms must
            survive into every derived artifact — including a JSON response.

            `strip_markup` removes TEI tags for readability and is **display
            only**, which the response states rather than leaving to be
            noticed: the stripped text no longer shares offsets with the
            witness, so an `EXACT_SPAN` verification built against it would
            record positions pointing nowhere. Raw is the default for exactly
            that reason."""
            try:
                record = source.fetch(ref)
            except Exception as e:  # noqa: BLE001 — reader errors are the client's answer
                raise HTTPException(status_code=404, detail=f"{type(e).__name__}: {e}") from e
            raw = record.text
            text = strip_markup_for_display(raw) if strip_markup else raw
            truncated = len(text) > max_chars
            return {
                "ref": record.ref,
                "witness_ref": record.witness_ref,
                "title": record.title,
                "locator": record.locator,
                "source_terms": record.note,
                "total_chars": len(text),
                "raw_total_chars": len(raw),
                "truncated": truncated,
                "markup_stripped": strip_markup,
                "offsets_align_with_witness": not strip_markup,
                "text": text[:max_chars],
            }

    # --- agent runs (the only endpoints that can spend money) ---------------

    if run_manager is not None:

        @app.get("/api/run/config")
        def run_config() -> dict[str, Any]:
            """What a run may cost and whether the server can start one at
            all. The browser needs this to render honest limits rather than
            letting someone type a budget the server will reject."""
            return run_manager.config()

        @app.get("/api/run")
        def run_status() -> dict[str, Any]:
            """`history` is this process's own runs, with their tool calls;
            `recorded` is every run in the event log, including ones started
            before the last restart. Both, because they answer different
            questions and neither subsumes the other: the live one is richer,
            the recorded one survives."""
            return {
                "current": run_manager.current(),
                "history": run_manager.history(),
                "recorded": run_manager.recorded(),
            }

        @app.get("/api/run/{run_id}")
        def run_detail(run_id: str) -> dict[str, Any]:
            run = run_manager.get(run_id)
            if run is None:
                raise HTTPException(status_code=404, detail=f"no run {run_id}")
            return run

        @app.post("/api/run")
        def run_start(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
            """Start one run of one or more agents.

            Accepts either `{instructions, agent_id, ...}` for a single agent or
            `{agents: [{...}, ...]}` for a swarm. Several agents share one
            process, one graph, one lock and one spend cap — see
            `cohort/ui/runs.py`.

            Every refusal here is a 409 with a reason meant to be read, not a
            400: "a run is already in progress", "that budget exceeds the
            server's ceiling", "no corpus is configured" are all states the
            researcher can act on, and flattening them to a validation error
            would throw away the only useful part.

            `{question_id, auto: true}` plans the roster instead of taking
            one — see `plan_inquiry`. The planning is server-side so the
            terminal gets the same rosters as the browser (`cohort run
            --question ID`), and because the browser does not know the model
            pool's families and so cannot tell which rosters the write
            boundary would refuse."""
            question_id = str(body.get("question_id") or "").strip() or None
            raw = body.get("agents")

            if body.get("auto"):
                if not question_id:
                    raise HTTPException(
                        status_code=422,
                        detail="an auto inquiry needs `question_id`: the "
                               "question is the agenda, and nothing here "
                               "invents one.",
                    )
                try:
                    with Graph.open_read_only(run_manager.db_path) as g:
                        node = g.get_node(question_id)
                    # Checked here as well as in `start`, and before planning
                    # rather than after: a claim payload also has a `text`, so
                    # planning first would build a whole roster around a claim's
                    # own words and only then be refused for the node's type.
                    if node.type != NodeType.QUESTION:
                        raise HTTPException(
                            status_code=422,
                            detail=f"{question_id} is a {node.type}, not a "
                                   "question. An inquiry runs against a question "
                                   "node; ask one first.",
                        )
                    payload = node.payload or {}
                    specs = plan_inquiry(
                        str(payload.get("text") or ""),
                        answerable_by=str(payload.get("answerable_by") or ""),
                        models=run_manager.config()["models"],
                        max_agents=run_manager.max_agents,
                    )
                except CohortError as e:
                    raise HTTPException(
                        status_code=404,
                        detail=f"no node {e}. An inquiry runs against a "
                               "question node; ask one first.",
                    ) from e
                except RunRejected as e:
                    raise HTTPException(status_code=409, detail=str(e)) from e
                return _start(specs, body, question_id)

            if raw is None:
                # single-agent shape, kept working: one agent is the common case
                # and callers (including the earlier UI) should not have to wrap
                # it in a list to say so
                raw = [{
                    "agent_id": body.get("agent_id") or "agent:ui-worker",
                    "instructions": body.get("instructions") or "",
                    "corpus_scope": body.get("corpus_scope") or "",
                    "method_label": body.get("method_label") or "",
                    "model": body.get("model") or "",
                    "role": body.get("role") or "",
                }]
            if not isinstance(raw, list):
                raise HTTPException(status_code=422, detail="`agents` must be a list")
            try:
                specs = [
                    AgentSpec(
                        str(a.get("agent_id") or ""),
                        str(a.get("instructions") or ""),
                        str(a.get("corpus_scope") or ""),
                        str(a.get("method_label") or ""),
                        str(a.get("model") or ""),
                        str(a.get("role") or ROLE_WORKER),
                    )
                    for a in raw
                ]
            except AttributeError as e:
                raise HTTPException(
                    status_code=422, detail="each agent must be an object"
                ) from e
            return _start(specs, body, question_id)

        def _start(specs, body: dict[str, Any], question_id: str | None) -> dict[str, Any]:
            try:
                return run_manager.start(
                    specs,
                    budget_usd=float(body.get("budget_usd") or 0.0),
                    max_turns=int(body["max_turns"]) if body.get("max_turns") else None,
                    question_id=question_id,
                )
            except RunRejected as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
            except (TypeError, ValueError) as e:
                raise HTTPException(status_code=422, detail=str(e)) from e

        @app.post("/api/run/stop")
        def run_stop() -> dict[str, Any]:
            """Ask the current run to stop after the turn in progress.

            Cooperative, not a kill: the in-flight model call is already paid
            for, and killing a thread mid-write could leave the projection and
            the log disagreeing — the one invariant the whole system rests on."""
            try:
                return run_manager.stop()
            except RunRejected as e:
                raise HTTPException(status_code=409, detail=str(e)) from e

    if FRONTEND_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app
