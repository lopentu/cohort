# Cohort

Cohort helps a researcher turn a research question about a corpus into
hypotheses backed by evidence: LLM agents propose claims that must cite real
passages and conjectures that must say what would prove them wrong, and only
the researcher can accept a finding.

A reviewing agent from a different model family checks each proposal. It can
stop a proposal from advancing, but cannot advance one on its own judgement.

The agents work with two kinds of record:

- **Claims** must cite passages in the corpus. Before a claim can advance,
  Cohort re-fetches every cited passage and checks that the quoted text is
  really there.
- **Conjectures** may go beyond what the cited passages say, which is how
  something new gets proposed. In exchange, a conjecture is refused unless it
  comes with a search that could refute it, plus a prediction of that search's
  result, recorded before the search is run.

Cohort also refuses to treat agreement between sources as independent support
when the sources are recorded as copies or parallels of one another. Every
proposal, check, refusal and decision is kept in an append-only event log.

Cohort is meant to work with any research question over any corpus. It was
developed on the Chinese Buddhist canon (CBETA), whose licence restricts
redistribution, so that corpus is not in this repository.

📖 **Documentation: [docs/index.md](docs/index.md).** 繁體中文：[快速上手](docs/quickstart-zh-TW.md)

## Try it: no corpus, API key or network needed

    uv sync --extra dev --extra ui
    uv run pytest -q
    uv run python demo.py

`demo.py` records a claim with two supporting witnesses. When a `parallel_of`
link between those witnesses is added, the claim still counts two witnesses,
but Cohort stops treating them as independent.

To use your own texts, list plain-text files in a `manifest.csv`; see
[docs/corpus.md](docs/corpus.md). Agent runs need an OpenRouter key: copy
`.env.example` to `.env`, then see [docs/agents.md](docs/agents.md).

## Where to go next

| If you want to… | Read |
|---|---|
| understand the idea and its rules | [docs/design.md](docs/design.md) |
| know what works today and what doesn't | [docs/handoff.md](docs/handoff.md) |
| pick up the current work toward a paper | [docs/handoff-paper-2027.md](docs/handoff-paper-2027.md) |
| use the browser UI or the CLI (they have the same features) | [docs/ui.md](docs/ui.md), [docs/cli.md](docs/cli.md) |
| run it in Docker or host it | [docs/docker.md](docs/docker.md), [docs/hosting.md](docs/hosting.md) |
| see what the docs cite | [docs/references.md](docs/references.md) |

## Using an AI coding assistant

Point it at [AGENTS.md](AGENTS.md). Claude Code and Gemini CLI load it
automatically, through `CLAUDE.md` and `GEMINI.md`. It gives the reading order,
the commands, the rules the tests enforce, and the data you must not commit.

## Two things not to assume

- **Cohort has no access-governance layer**: no allowlists, no retention rules,
  no deletion checks. That belongs to a separate system, ATELIER, which is not
  connected ([design.md](docs/design.md) §2).
- **"Attested" means cited and located, never "true".** Only the researcher's
  `accept` makes a finding citable.
