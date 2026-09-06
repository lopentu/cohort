# Design spec

*Evidential pluralism made auditable. A supervised evidence graph for
multi-agent textual research.*

Track: infrastructure, within Sindia.
Venue: PNC 2026, as a demo of Sindia.

**Scope decision: built standalone.**

> **This is the design, not the status.** Its original status line read
> *"design settled, stage 1 built, stages 2 onward unbuilt"*, which was true
> when written and is not now: stages 1–5 are built and live-verified. Sections
> that describe a moment rather than an intention (§11's test count, §12's
> table, §14's open decisions) are annotated in place. For current state read
> [handoff.md](handoff.md); for how it got there, [changelog.md](changelog.md).

---

## 0. How to use this document

A spec for an implementing agent and for the humans reviewing it. Sections 1 to
5 are the framing and the constraints; read them before writing anything.
Sections 6 to 9 are the design proper. Section 11 is what existed at the time of
writing, section 12 the build order, section 14 the decisions that are still
open. (This paragraph pointed at 12, 13 and 15 until 2026-09-02, off by one
against its own headings.)

Standing rule for the implementing agent: when a rule here cannot be honoured,
say so and stop. Do not implement something that looks like it honours the rule.
The predecessor's central problem was documentation describing guarantees the
code did not provide.

---

## 1. The thesis

From the project lead, and this is the framing sentence for the whole system:

> 面對歷史語料的複雜度，我們不是要讓輔助研究的 agents 做 consensus-seeking，
> 比較像是把它定義成 **evidential pluralism made auditable**，最理想還可以
> propose 可能的 hidden patterns/theory。

Three commitments follow, and every design decision below serves one of them.

**Pluralism, not consensus.** Multiple agents produce multiple readings, and
disagreement between them is preserved as structure rather than resolved into a
single confident answer. Nothing in this system votes, averages, or scores
confidence by counting agreement.

**Auditable.** Every node carries its source and its author; every promotion in
status carries who did it and why; every refusal is recorded. The audit trail is
an output, not a debugging aid.

**Proposes hidden patterns.** The system is allowed to say something not already
in its sources, on one condition: it must name what would refute the proposal.
See section 7, which is the contribution.

**Contribution is at 工具層, not 內容層.** The deliverable is methodological
infrastructure for (Buddhist) DH. It is not an argument about textual history,
and it should not be dressed up as one. This scopes the demo: what gets
demonstrated is that the machinery refuses the right things.

---

## 2. Scope: standalone, and what that forbids

COHORT is the swarm and evidence-graph layer. ATELIER, the existing governance
layer (which source, under what licence, approved by whom, what was taken, what
was kept, verified deletion) stays a separate working system and is integrated
later, not now.

**What COHORT gets instead.** A thin source interface, `search(query)` and
`fetch(ref)`, with one local implementation over text held on disk. No policy
file, no allowlist, no caps, no retention rules, no deletion verification.
Deliberately minimal, because governance is ATELIER's job and a weak version of
it here would produce two half-answers.

**Keep the seam narrow, and shaped like ATELIER's.** ATELIER's adapter interface
is already `search` / `fetch`. Match it exactly. Integration then means writing
one adapter class rather than reshaping the swarm. Do not design COHORT's
internals around anything else ATELIER does; the coupling should be one function
signature wide.

**Two rules this phase must not break.**

1. **Public-domain or locally-held material only.** This is what makes building
   without a governance layer legitimate rather than a shortcut. Pointing COHORT
   at a restricted source before ATELIER is under it turns a staging decision
   into a hole.
2. **Claim no governance.** No retention language, no rights-aware framing, no
   deletion guarantees in the README, the report, or the talk while ATELIER is
   unplugged. Say plainly that access governance is a separate system, currently
   not connected. Overclaiming here would repeat the exact failure the previous
   build spent a phase fixing.

**Where the layers meet later.** COHORT's source interface becomes an ATELIER
adapter, and ATELIER's cumulative-coverage question (a persistent graph of
offsets and counts can, at sufficient density, approximate a copy) becomes a
real design item at that point. Note it now; do not solve it now.

---

## 3. Where this sits in Sindia

Infrastructure serves the other legs rather than competing with them. In this
phase COHORT is developed as its own tool, so any dependencies on sibling
work are what it *will* owe, not what it owes this month. (Team and
cross-project details have been omitted from this copy.)

---

## 4. What the reference model got right, and what it got wrong

The direction came from a description of a graph-native research swarm: many
agents in parallel, every source a node, every node linked, claims weighted by
how many sources back them.

**Keep.** The evidence graph as primary artifact, rather than a report. Linking
as sources arrive, not as a later cleanup pass. Every claim traceable to
something openable. Contradictions surfaced as labelled edges instead of buried.

**Reject, and this rejection is the paper.** Corroboration weighting. The
reference model's core mechanic is that N independent sources agreeing raises
confidence, which is a fact-checking model borrowed from finance, where a figure
is either right or wrong.

For a transmitted corpus it is inverted. Agreement between witnesses usually
indicates shared descent, not independent confirmation. Two witnesses in a
copying relation agreeing is the expected consequence of that relation and
carries almost no evidential weight; counting it as corroboration is the error
stemmatology exists to prevent. Two parallel passages agreeing are not two
observations, they are one transmission event seen twice.

This is the same commitment as 不做 consensus-seeking, arrived at from the
philological side. What replaces edge-counting:

- attestation spread across distinct works and authors, not across records;
- dating confidence, and the route by which a date was assigned;
- explicit non-independence edges wherever descent or parallelism is known;
- divergence *within* a lineage, which is the genuinely informative signal.

Stated for the talk: *corroboration weighting assumes source independence;
transmitted corpora violate that assumption systematically; here is what we
weight instead.* No general-purpose research swarm can make that argument.

**Fan-out is not a headline.** With 本地大算力, running a multi-agent system is
not the constraint. That makes the discipline of the design the interesting
part, not the agent count. In this phase parallelism is bounded by the local
corpus and by good manners; access-mode gating belongs to ATELIER and arrives
with it.

> **Superseded, see `roadmap.md` "Scope revision".** After comparing against
> a parallel project, agent count is now allowed to grow, conditioned on
> demonstrating declared viewpoint diversity rather than being the claim
> itself. Recorded here rather than deleted, per this document's own rule
> that a superseded guarantee must say so, not go quiet.

---

## 5. Design principles

Seven, ordered by how much damage violating them does.

1. **The append-only event log is ground truth; the graph is a projection.**
   Every mutation is a logged event with an author and timestamp, appended and
   flushed as it happens. The graph is rebuildable from the log, and a rebuild
   test asserts it. If the two disagree, the log is right and the projection has
   a bug.

2. **Nothing in the graph is true.** No fact assertions. Everything is
   attested-by, contradicted-by, descends-from, or parallel-to. This is an
   evidence graph, not a knowledge graph: for this material, the assertions an
   ontology would encode (translated in year Y by translator Z) are exactly what
   is contested.

3. **Agents communicate only through the graph.** No agent-to-agent messaging,
   no shared transcript. An agent reads the graph, calls tools, writes back.
   This is a blackboard architecture in the Hearsay-II sense, and it buys three
   things: every contribution has an author, cost is linear rather than
   quadratic in agent count, and the researcher can pause the system at any
   moment because the entire shared state is one inspectable object.

4. **Tools are the only writers.** No agent emits graph structure directly.
   Writes go through named functions and invariants are enforced there. A rule
   enforced in a prompt is a request; a rule enforced at the write boundary is a
   property.

5. **Node identity comes from the source.** A passage is named by its canonical
   reference. Two agents finding the same passage converge on one node with two
   authorship records. Hashing agent-produced text into identity fragments the
   graph silently, which makes the system look more productive as it becomes
   less correct.

6. **The researcher holds the only signature that matters.** Agents verify; only
   the researcher accepts. Only accepted nodes may be cited by output or used as
   premises by other agents. Rejection is a first-class act that persists with
   its reason.

7. **Single writer.** One process owns the database connection; workers are
   read-mostly and hand writes to the owner. Many agents against SQLite is lock
   contention, not parallelism.

---

## 6. Vocabulary

Closed on purpose, small enough for one slide. A vocabulary that grows whenever
something does not quite fit becomes an ontology project. Adding a type requires
an argument.

**Nodes.**

| Type | Meaning |
|---|---|
| `witness` | a text as transmitted: an edition, a recension, a manuscript |
| `passage` | a located span within a witness |
| `claim` | an assertion that must cite passages |
| `conjecture` | an assertion allowed to exceed its evidence, if testable |
| `query` | a retrieval that was run, or that would test a conjecture |
| `decision` | a researcher judgement, kept as part of the record |

> **One node type added since**: `verification`, one recorded verification
> attempt against another node, carrying method, result, assurance level and a
> `limitations` field. Its argument: §8 lets agents perform mechanical checks,
> and a check whose outcome is not itself a node cannot be audited, contested or
> superseded. Like `decision`, it is an audit record rather than evidence, and
> `citable()` excludes both. Full table in
> [vocabulary.md](vocabulary.md).

**Edges.**

| Type | Domain | Meaning |
|---|---|---|
| `attests` | passage to claim or conjecture | the evidential edge |
| `contradicts` | any to any | disagreement made visible |
| `parallel_of` | passage or witness | shared transmission |
| `descends_from` | passage or witness | makes agreement non-independent |
| `quotes` | passage to passage | citation within the corpus; makes agreement non-independent (a quotation is not a second witness) |
| `tests` | query to conjecture | the falsifiability edge |
| `supersedes` | same type to same type | revision |

> **Three edge types added since**, each with its argument, per this section's
> own rule that adding a type requires one:
>
> - `part_of` (passage → witness) — §11 below flagged passage-to-witness being a
>   payload field as a weak point, because it made `independent_support()` read
>   JSON out of a payload to answer this system's central question.
> - `verifies` (verification → witness/passage/claim/conjecture) — attaches the
>   audit record above to its subject.
> - `searched_for` (query → claim/conjecture) — records the retrieval that
>   produced a node, which is what makes `propose_claim`'s grounding query and
>   `propose_conjecture`'s prior-art search auditable rather than merely
>   promised.

Authorship is a field on every event, not an edge; an `authored_by` edge would
duplicate it with no way to keep the two consistent.

Every `witness` carries a dating record: a value that may be null, a confidence,
and a basis that must be a real sentence. Declining to date something is a
legitimate answer that still owes a reason. Routes: `dated`, `attributed`,
`source_label`, `unknown`. **This is the piece CWN.dia can reuse directly.**

---

## 7. Claims and conjectures: the falsifiability gate

The brief contains a contradiction that has to be resolved rather than papered
over. A system that only says what its sources already say cannot propose hidden
patterns. A system that proposes them is by definition saying something not yet
in its sources. Tightening the grounding does not fix this; it only makes the
system quieter.

The resolution is two object types with different obligations.

**Claims** must cite nodes. A claim with no `attests` edge cannot be verified
and the write boundary refuses to advance it. Conventional retrieval-grounded
generation, and not the interesting half.

**Conjectures** may exceed their evidence, which is what makes them useful. In
exchange, a conjecture must arrive with at least one query whose result would
confirm or refute it. A conjecture's provenance is not *which node supports
this* but *which retrieval would settle it*. Without a `tests` edge the write is
refused.

This is the anti-fabrication mechanism, and it beats citation checking twice
over: it permits genuine novelty, which citation checking cannot, and it filters
vacuous grounded claims, which citation checking passes happily, because a claim
can be perfectly cited and say nothing.

This answers 最理想還可以 propose 可能的 hidden patterns/theory directly, and it
is the contribution. If time runs out and only one thing ships beyond the
plumbing, ship this.

Usable lineage for the paper: a Popperian constraint implemented at a write
boundary. In the Buddhist frame it sits close to 因明, where an inference
lacking a valid ground (因) is not weak but formally defective, with a taxonomy
of defective grounds (似因). One sentence of that in the talk earns goodwill;
more than one invites a content-layer fight you do not want.

---

## 8. The promotion ladder

Researcher authority as mechanism rather than sentiment. A status on every node.

```
proposed  ->  attested  ->  accepted
    \             \
     \             ->  rejected
      ->  rejected
```

- `proposed`: an agent wrote it.
- `attested`: a mechanical check passed. The passage exists, the citation
  resolves, the reference is well formed. **Agents may do this.**
- `accepted`: the researcher signed it. **Only the researcher.**
- `rejected`: the researcher threw it out, with a reason.

Enforced at the write boundary:

- No rung may be skipped.
- A claim or conjecture cannot be attested with nothing attesting it, or
  `attested` would mean nothing.
- Only accepted nodes are citable by output or usable as premises by other
  agents. An agent cannot build on a finding the researcher has not signed.
- Rejection requires a stated reason and persists. A rejected node cannot be
  re-proposed by the next worker along; reopening is a researcher action.

That last rule stops the swarm from rediscovering what has already been refused,
and it makes the record of rejections, with reasons, part of the scholarly
output. Worth pointing at in the talk: the graph records the judgement calls,
not only the findings.

---

## 9. Anti-goals

Each is a plausible wrong turn that would look like progress.

- **Consensus-seeking.** Voting, averaging, majority readings, or any mechanism
  that resolves disagreement instead of preserving it. Named by the project lead
  as the thing this is not.
- **Confidence scores computed from edge counts.** Section 4.
- **A knowledge graph of asserted facts.** Principle 2.
- **Agent-to-agent conversation.** Unauditable and quadratic. Principle 3.
- **An open node or edge vocabulary.** Section 6.
- **Reimplementing governance inside COHORT.** Section 2. A weak policy layer here
  competes with a working one next door and makes the eventual integration
  harder.
- **Claiming governance COHORT does not have.** Section 2, rule 2.
- **Content-layer claims.** 工具層 contribution. Do not ship an argument about
  textual history dressed as a demo.
- **Agent count as a headline number.** A scale claim, not a mechanism.
  **Superseded, see `roadmap.md` "Scope revision"** — allowed now when it
  demonstrates declared viewpoint diversity, not scale for its own sake.

---

## 10. The visualization leg

A (dynamic/temporal) KG visualization, tied into this architecture, is
wanted elsewhere in the program. One caution, and it is a real one.

This graph is deliberately not a knowledge graph, so a naive projection into one
flattens exactly the epistemics that justify the system. If the visual shows
nodes without status, and edges without the independence flag, it silently
restores the consensus illusion: a densely linked node looks well supported
regardless of whether its support is independent.

Requirements for the projection:

- node status (`proposed` / `attested` / `accepted` / `rejected`) is a visual
  channel, not a tooltip;
- `descends_from` and `parallel_of` are visually distinct from `attests`, because
  they *discount* rather than add support;
- contradiction edges are as visible as agreement edges;
- clicking any node reaches its provenance.

Done well this is the strongest artifact in the whole showing, because it makes
evidential pluralism legible at a glance. Done naively it argues against the
thesis.

---

## 11. What already exists (stage 1)

> **As of when this was written.** 22 tests then, 260 now, and stages 2–5 are
> built. Kept because the *shape* it describes is still the shape, and because
> its "known weak points" list below is the best record of four real defects.
> Current state: [handoff.md](handoff.md).

A working write boundary, 22 tests, an offline demo. No agents, no corpus, no
model, no network. Everything in sections 5 to 8 enforceable without a corpus is
enforced and tested.

```
cohort/
├── schemas.py     closed vocabulary; nodes, edges, events, dating
├── errors.py      one exception per rule the design claims
├── eventlog.py    append-only JSONL, flushed per event, monotonic seq
├── graph.py       SQLite projection, the only writer, ladder, rebuild
tests/test_graph.py
demo.py
```

*The package currently ships under an earlier name; rename to `cohort` before
stage 2. Mechanical, no design change.* — **Done.**

Enforced and tested: source-derived identity with author accumulation; edges
never creating endpoints; edge domain constraints; the falsifiability gate,
including a conjecture smuggled in through the wrong function being permanently
unattestable; the full ladder with authority checks; persistent rejection
blocking re-proposal; `citable()` returning only accepted nodes; rebuild from
log matching the live projection exactly; a refused write leaving an honest log.

`independent_support()` implements section 4: attesting count, distinct
witnesses, and any descent or parallel relation between them. The demo shows a
claim whose support count stays at two while its independence flag flips to
false as soon as a `parallel_of` edge is recorded. **Show this first.** It is
the counter-argument to consensus-seeking in three lines of output.

**Known weak points, to fix in stage 2 rather than discover later.**
**All four are fixed** — kept here because naming them in advance is why they
were fixed rather than discovered.

- ~~Passage-to-witness is a payload field, not an edge, so `independent_support`
  reads JSON out of a payload.~~ Now the `part_of` edge, added deliberately to
  the vocabulary as §6 requires.
- ~~`contradicts` is stored as written and is not symmetric on read.~~ Now in
  `SYMMETRIC_EDGE_TYPES` with `parallel_of`: both are stored in both directions,
  so a query either way finds them, and the UI de-duplicates when drawing.
- ~~No concurrency test.~~ Two now: `SingleWriterViolation` on a second writer,
  and a real-overlap assertion proving `run_swarm()` workers run concurrently
  rather than sequentially.
- ~~`rebuild` writes a stray replay log.~~ It replays into
  `Graph(":memory:", event_log=None)`, so no log is written at all.

---

## 12. Build order

Each stage leaves something runnable. Do not start a stage before the previous
one has tests.

| Stage | Deliverable | Agents |
|---|---|---|
| 1 | Graph store, event log, vocabulary, ladder, rebuild. **Done.** | none |
| 2 | Thin source interface + local reader; tool layer; `part_of` edges; one worker that finds attestations. **Done, live-verified.** | one |
| 3 | Conjecture generation behind the falsifiability gate; persistent rejection in a live loop. **Done, live-verified.** | one |
| 4 | `parallel_of` / `descends_from` edges from existing markup; contradiction surfacing; `independent_support` over real witnesses. **`parallel_of`, collation and `contradicts` done; `descends_from` blocked** — no corpus channel asserts descent. | few |
| 5 | Fan-out with real concurrency; researcher UI with graph view, accept/reject, provenance on click. **Done, live-verified**, plus corpus browsing and a run launcher. | many |
| 6 | ATELIER integration: the source interface becomes an adapter; cumulative-coverage policy | unchanged |

> Stage-by-stage detail is in [roadmap.md](roadmap.md); what is left is in
> [handoff.md](handoff.md).

**If time runs short, cut 5 before 3.** A small graph with a working
falsifiability gate is a contribution. A large swarm without one is the thing
being critiqued. Stage 5's UI overlaps the visualization leg (section 10);
coordinate rather than building two viewers.

Stage 2 notes: tools are named, schema-validated and individually refusable. An
agent may call `find_attestations` or `propose_conjecture`; nothing exposes a way
to write arbitrary structure or request a whole corpus. The source interface is
`search` / `fetch` and nothing more (section 2).

Stage 5 is where the single-writer discipline stops being a comment and starts
needing a test. Write the contention test before the fan-out.

---

## 13. Reuse rather than rebuild

Carry into COHORT by hand, with tests. ATELIER stays a separate system, so this is
copying a pattern, not taking a dependency.

- Dating assignment with a stated basis, and `unknown` as a real answer. It now
  lives on `witness` nodes.
- The habit that made the old build survive review: the report counted its own
  outputs instead of asserting facts about them. Any claim a document makes
  about the system should be arithmetic, not assertion.

Do not port the policy guard, the ephemeral store, or the retention machinery.
Those are ATELIER's, they work, and duplicating them here produces two weaker
versions of one thing.

---

## 14. Open decisions

Do not guess at these.

**Development corpus.** Must be public-domain or locally-held (section 2, rule
1), and small enough to iterate on. Michael's Buddhist material may qualify; so
may a CBETA or Kanripo checkout. Confirm before stage 2.

> **Resolved, see `roadmap.md` "Scope revision".** CBETA v061 is the
> confirmed corpus, accepted as "locally-held" under section 2 rule 1 with
> its real license terms preserved through the pipeline, not waived.

**Corpus format.** Does the data carry parallel or cross-reference markup
already? If yes, the first `parallel_of` edges are free
and stage 4 is close. If it is bare text, alignment becomes the first hard
problem and the project shape changes.

> **Answered: it carries markup, and the first `parallel_of` edges were
> free.** The channel is `<cb:docNumber>` (not generic TEI pointers, which are
> rare), and `<app>`/`<lem>`/`<rdg>` apparatus is pervasive — 271 of 300 sampled
> files cite two or more editions. One caution the answer came with: joint
> sigla like `【宋】【元】【明】【宮】` are *one* shared-descent family, not four
> confirmations. Details in [corpus.md](corpus.md).

**Chronology.** **Still open — do not guess.** What replaces political-dynasty
periodization? For translation
material, translation date, composition date and recension date are three
different things and the translator matters more than the dynasty. Coordinate
with CWN.dia, which has the same problem in a different corpus.

**Name.** COHORT is deliberately unrelated to the content, which avoids
overclaiming and avoids grepping for a corpus term inside its own package.
`cohort` is taken on PyPI by an MIT electromagnetics simulator, which does not
matter for an internal project and would matter for a published one. Do not
backronym it.

---

## 15. The claim the paper makes

> Agentic research systems currently import a verification model from
> fact-checking: many sources agreeing raises confidence. Transmitted textual
> corpora violate the independence assumption that model requires, because
> agreement between witnesses is usually evidence of shared descent rather than
> independent confirmation. COHORT proposes evidential pluralism made auditable: an
> evidence graph in which nothing is asserted as true, relations of descent and
> parallelism are first-class, claims must cite their sources, conjectures must
> arrive with what would refute them, and only the researcher can promote a
> finding to citable status. The result is a system that proposes hidden
> patterns without generating false ones, and whose refusals are part of its
> scholarly output.
