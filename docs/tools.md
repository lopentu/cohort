# The tool layer

Tools are the **only writers**. No agent emits graph structure directly; every
write goes through a named, schema-validated function, and the invariants are
enforced there rather than requested in a prompt
([design.md](design.md) §5 principle 4).

Each tool is task-shaped and individually refusable. Nothing exposes a way to
write arbitrary structure or to request a whole corpus.

Every signature is `(graph, source, args, *, authored_by, model_call_id=None)`
— except `record_contradiction`, which takes no `source` because it reads only
the graph.

## What refusal means here

A tool that cannot do its job **raises**, and the failure is written to the
event log by `Graph.log_refusal()`. This is not error handling; refusals are
part of the output ([design.md](design.md) §15). Read them back with
`read_refusals()`, or see them in the UI's refusal panel.

Every rule a tool raises is a **named** `CohortError` — `UngroundedClaim`,
`WrongNodeType`, `SourceRefMissing`, `InvalidVerdict` alongside the write
boundary's own — because the refusal census reads the rule's *name*
([refusals.md](refusals.md)). Until the first live run was censused these were
bare `ValueError`s, and a claim the corpus would not support was indistinguishable
in the record from a mistyped id. `tests/test_refusal_census.py` now fails if a
tool raises anything the taxonomy cannot name.

The most important refusal is an invented node id. Agents guess ids — a live
run produced five such guesses — and every one is refused rather than minting a
node, because edges never create their endpoints. When the id is a *near* miss
— the right uuid with its type prefix dropped, which three models on three
model families all did in one run — the refusal names the node it nearly
matched instead of stopping at "not found". It is still refused: the prefix is
what makes an id say what kind of thing it names, and quietly repairing it
would teach that the type is decoration.

## The six tools a worker may call

### `propose_claim`
Creates a `claim`: an assertion the sources state.

    text: str              the claim
    grounding_query: str   run against the corpus BEFORE the claim is created

The grounding query is **actually run first**. Zero hits refuses the write, and
the refusal explains the alternative rather than just saying no: a claim with no
passages to cite could never be attested, so if the point is that something does
*not* occur in the corpus, that is a conjecture — an absence is settled by a
retrieval, not by citation.

On success it records the query as a `query` node with its hit count and links
it `searched_for` → claim, so the grounding is auditable rather than implied.

> This tool was added after a live run in which an agent, having no way to
> create a claim, fabricated node ids five times trying to attest one that
> didn't exist. See [changelog.md](changelog.md).

### `find_attestations`
Searches the corpus and records each hit as evidence.

    claim_or_conjecture_id: str
    query: str
    max_results: int = 5   (1–20)

    → FindAttestationsReport(passages: list[str], witnesses: list[str])

Each hit becomes a `witness` (converging with any existing one for the same
ref), a `passage` located in it via `part_of`, and an `attests` edge to the
target. The passage is attested immediately — "the passage exists, the citation
resolves" is exactly the mechanical check an agent may perform.

Witnesses are proposed with `DatingRoute.UNKNOWN` and a stated basis, not left
undated.

**Whether the target itself advances depends on who called.** For a claim the
caller did *not* author, the tool closes the rung: the citations were fetched
and resolved, which is what `attest` means. For the caller's own claim it does
not, and does not try — an agent may not attest what it authored
([vocabulary.md](vocabulary.md)), so the tool asks `attest_conflict()` rather
than writing a refusal that was certain in advance. The evidence is still
recorded; the claim waits at `proposed` for a reviewer or for the researcher.

> `witnesses` is returned because the stage-4 tools take a *witness* id. Before
> that, an agent that had just called this tool had no way to obtain one — so it
> guessed four times in a row and was correctly refused each time. Every one of
> those refusals was unavoidable, which made it a gap in the tool rather than a
> mistake by the model.

### `propose_conjecture`
Creates a `conjecture` — an assertion allowed to exceed its evidence.

    text, derivation, corpus_boundary, selection_risks,
    alternative_explanations, prior_art_query, tests_query_text,
    tests_expectation, tests_expected_hits

All required, none blank. The `prior_art_query` is run against the corpus
*before* proposing. The `tests_query_text` becomes a `query` node linked `tests`
→ conjecture, which is what makes the conjecture attestable at all — and it now
carries the author's **prediction** about what that query will return
(`at_most`/`at_least` and a count), recorded in the same call, on a payload
nothing can edit afterwards. A prediction stated after the result is known is
not a prediction.

This is the falsifiability gate, and it is the contribution: it permits genuine
novelty, which citation checking cannot, and it filters vacuous grounded claims,
which citation checking passes happily.

### `record_contradiction`
Writes a `contradicts` edge with a **mandatory stated reason**.

    node_a_id: str
    node_b_id: str
    reason: str

Both ids must already exist — invented ids raise `NodeNotFound`. Only
`claim`, `conjecture`, `passage` and `witness` may be contradicted; audit nodes
(`verification`, `decision`) are refused, since a bookkeeping record disagreeing
with something isn't a scholarly disagreement.

The `reason` is stored on the edge (migration 3). Edges have no ladder and no
retraction, so an edge that carries an argument must carry its argument with it.

### `link_parallels`
Reads a witness's own CBETA `<cb:docNumber>` cross-references and writes
`parallel_of` edges.

    witness_id: str

    → LinkParallelsReport(witness_id, linked, already_linked,
                          absent_from_graph, unresolved, not_asserted)

Every category is reported rather than collapsed into a success count, because
what it *didn't* link is the interesting part. It refuses to mint an edge from:

- **`cf.` and `Part of` references** — curatorial "compare", sometimes
  deliberately vague. A `parallel_of` edge has teeth: it *suppresses*
  independent support. Minting one from `[cf. No. 220(4 or 5) etc.]` would
  silently discount real evidence on weak grounds — the exact failure the whole
  design exists to prevent.
- **ambiguous Taishō resolutions** — a bare number can resolve to several
  witnesses, so it returns every candidate rather than guessing.
- **witnesses not already in the graph** — no endpoint minting.

### `collate_editions`
Records a `cross_edition_collation` verification for a witness, reporting which
edition families its TEI `<app>` apparatus cites.

    witness_id: str  →  verification node id

**Joint sigla are never split.** `【宋】【元】【明】【宮】` appears as a single
`wit` value 2,155 times in a 300-file sample; counting it as four independent
confirmations is precisely the error this system exists to prevent, so it is
reported as one shared-descent family. The verification always carries
`limitations` stating what collation did not establish.

## The evidence tools a worker may call (with `--radich`)

Three read-only tools over Radich's pre-450 corpus, registered on a worker only
when the server was started with `--radich PATH` (and, for the third, with
`EVIDENCE_EMBEDDINGS_PATH` set). They write nothing, so the write boundary
never sees them; what a model reads from them becomes structure only through
`propose_claim` and `propose_conjecture`, where the rules bite. Their system
prompt addendum (`EVIDENCE_CONTRACT`) forbids proposing a translator as a
claim: the tools give a leaning, not an attribution.

They are meant to be chained, and each output carries what the next needs:

    attribution_evidence(uid)              -> a leaning, and the strings behind it
    semantic_neighbors(uid)                -> other works whose passages read like it
    align_passages(uid, neighbour)         -> verbatim overlap, with citable offsets
    attribution_evidence(uid, withhold=[neighbour])  -> does the leaning survive?

### `attribution_evidence`

What the Evidence tab shows, minus the painted text: verdict (`leans` /
`low evidence` / `no evidence`), leader and runner-up with margin, the painted
pair and the strings pulling each way with **raw counts** in each profile, the
units and feature tokens left in every class after the target's own Taishō
work was withheld, and provenance (file hashes, code version). `withhold`
removes further units first — the sensitivity test. `features` chooses Radich's
curated strings or the label-free vocabulary drawn from grey texts.

### `semantic_neighbors`

For each 400-character window of the unit, the most similar windows in *other*
works by a frozen Buddhist-Chinese encoder, with excerpts of both sides, and a
tally of which unit the nearest window belongs to across all windows. Same-work
windows are always excluded. The encoder is at the largest-class baseline for
translator identity, so the tally is content likeness, never attribution; its
use is to surface quotation, parallels and commentary — the dependencies that
make string counts non-independent.

### `align_passages`

The share of one unit's ten-character strings found verbatim in another, both
ways, and the longest shared runs with offsets into each original text.
Computed on Han characters only: CBETA's punctuation and line breaks are
editorial and would break every run (T0603/T1694 read as 11% with them in and
65% with a 279-character run without). Under 1% is what unrelated texts show.

## The reviewer's tool

### `review_claim`
Not on a worker's list. `ReviewWorker` has this and `record_contradiction` and
nothing else — see [agents.md](agents.md).

    claim_id: str
    verdict: "sound" | "unsound" | "indeterminate"
    detail: str    what you checked, recorded verbatim

Re-fetches every passage citing the claim and re-locates its excerpt
(`verify_exact_span` per passage), then records **one** verification node
against the claim and advances it to `attested` only if every span re-verified
*and* the verdict is `sound`.

The asymmetry is the whole design: **a verdict can withhold promotion, never
supply it.** `sound` over a citation that fails to re-fetch does not advance the
claim, because promotion rests on the mechanical check and not on what a model
said. This is what keeps a reviewer from being the `MODEL_ENTAILMENT` method
that `VerificationMethod` deliberately refuses to admit.

Where the words go matters too. `detail` carries what the machine established;
the reviewer's own reading goes in `limitations`, the field for what a passing
check does *not* establish. Separate fields are what stop a confident sentence
from reading later as a mechanical finding.

**Always**, including a `sound` verdict. That used to be the exception, on the
reasoning that a positive verdict is not a limitation, and the negative control
(`scripts/run_negative_control.py`) showed what the exception cost: a reviewer
handed a claim with one altered excerpt returned `sound` with *"Re-fetched and
re-verified the cited passages… confirming that the title indeed appears in the
corpus"*, and that sentence was written into `detail` on a verification whose
result was `fail`. A sound verdict over a failing check is not corroboration;
it is the most important thing on the record to mark as not established.

It refuses a claim the caller may not attest *before* re-fetching anything —
`attest()` would refuse at the end anyway, but a reviewer that has already
spent the fetches has learnt the rule too late to act on it.

The report also carries `distinct_witnesses` and `independent`, because an
author has no incentive to look and a researcher reading the verification
should not have to ask separately.

## Not an agent tool

### `run_prospective_test`
Re-runs a conjecture's prospective query and compares the hit count to the
prediction recorded when it was proposed.

    conjecture_id: str  →  ProspectiveTestReport

The falsifiability gate has always demanded a query that would settle a
conjecture going forward, and `attest()` has always refused a conjecture with no
`tests` edge. Between them they checked that a test *existed*. Nothing ran it.
A gate that demands a prediction and never collects on it is a gate on
paperwork.

It is a `VerificationMethod` (`prospective_test`) where `MODEL_ENTAILMENT` is
not, because nothing in it is anyone's opinion: a stored query is re-run and a
stored integer is compared to the count that comes back. It is also the only
method that can fail on **new evidence** rather than on a broken record — every
other one asks whether the record still holds up, this one asks whether the
world still agrees.

**It grants no assurance rung**, passing or failing. The ladder grades how well
a node's citations stand up; a surviving prediction says something else, and
giving it a rung would repeat the A3 mistake of grading one thing with a name
that reads as another.

Here the *count* is the finding, so a search that returns the cap has been
floored rather than counted. A floor settles `at most E` only when it already
exceeds E, and `at least E` only when it already reaches it; otherwise the
result is `indeterminate` and says so. Counting a capped result as exact is how
a measurement layer starts publishing numbers it did not measure.

Not registered for agents, same reasoning as `verify_exact_span` below: its
whole value is in being run *later* — against a rebuilt index or a corpus that
has grown — and an agent running it in the turn that proposed the conjecture
would be testing a prediction against the state that produced it.

### `verify_exact_span`
Re-fetches a passage's source and confirms the excerpt is still there, byte for
byte, recording an `exact_span` verification at `A2`.

It is **deliberately not registered** for agents: it is a researcher-side
integrity check, not an agent write. `find_attestations` stores `source_ref` on
every passage precisely so this re-fetch remains possible later.

## Why the stage-4 tools are safe to register

`link_parallels` and `collate_editions` write structure with real epistemic
consequences, and were held back for a while on that basis. What settled it:
**neither takes a judgement as input.** Both accept only a `witness_id`; the
content comes from the corpus's own markup. The model chooses *what to read*,
not *what is true* — the same discretion `find_attestations` always had.
