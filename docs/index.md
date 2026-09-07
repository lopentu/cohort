# COHORT documentation

*Evidential pluralism made auditable — a supervised evidence graph for
multi-agent textual research.*

## Which document answers which question

| I want to know… | Read |
|---|---|
| What is this and why does it exist? | [design.md](design.md) — the spec |
| What's true right now? What's left? | [handoff.md](handoff.md) |
| How does it actually work inside? | [architecture.md](architecture.md) |
| What are the node and edge types? | [vocabulary.md](vocabulary.md) |
| What can an agent do, and what will it be refused? | [tools.md](tools.md) |
| The system refused 40 writes — which should I read? | [refusals.md](refusals.md) |
| How do I run agents, and what does it cost? | [agents.md](agents.md) |
| How do I point it at a corpus? | [corpus.md](corpus.md) |
| How do I use the web interface? | [ui.md](ui.md) |
| What command do I run? | [cli.md](cli.md) — the `cohort` CLI, same capabilities as the UI |
| Why is it built this way? What got reversed? | [decisions.md](decisions.md) |
| What's the plan and how far along is it? | [roadmap.md](roadmap.md) |
| How did it get here? | [changelog.md](changelog.md) |
| Where do the talk's numbers come from? | `scripts/experiments/README.md` — one command per number |

## Start here

**If you're picking this project up fresh**, read in this order:
[design.md](design.md) §0–§9 for the framing and constraints, then
[handoff.md](handoff.md) for current state, then
[architecture.md](architecture.md).

**If you want to see the point in ten seconds**, no corpus or API key needed:

    .venv/bin/python demo.py

It prints a claim whose support count stays at two while its independence flag
flips to false the moment a `parallel_of` edge is recorded. That is the
counter-argument to consensus-seeking, in three lines of output.

**If you don't write Python**, the same functionality is in the browser —
see [ui.md](ui.md).

## The argument in one paragraph

Agentic research systems import their verification model from fact-checking:
many sources agreeing raises confidence. Transmitted textual corpora violate the
independence assumption that model requires, because agreement between witnesses
is usually evidence of shared descent rather than independent confirmation.
COHORT is an evidence graph in which nothing is asserted as true, relations of
descent and parallelism are first-class, claims must cite their sources,
conjectures must arrive with what would refute them, and only the researcher can
promote a finding to citable status.

## Two things to know before reading anything else

**Access governance is a separate system and it is not connected.** COHORT has
no policy file, no allowlist, no request caps, no retention rules and no
deletion verification. That work belongs to ATELIER. Nothing here should be read
as providing any of it — see [design.md](design.md) §2 rule 2, which forbids
claiming otherwise.

**A document about this system reports arithmetic, not assertion.** Count the
outputs rather than claiming things about them. Where a live run failed or a
capability is untested, these documents say so; if you find one that doesn't,
that's a bug in the document.
