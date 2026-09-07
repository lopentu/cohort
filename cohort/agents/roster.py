"""Model-family separation for a multi-agent run.

COHORT allows more than one agent only when the extra agents demonstrate
*declared viewpoint diversity* — distinct corpus scope and method — rather than
scale for its own sake (docs/roadmap.md "Scope revision"). The run launcher says
as much to the researcher: "give two agents different ones and their
disagreement means something."

That sentence was not true while every agent ran the same model. Two agents on
one model share training priors, prompt-shaped convergence and the same failure
modes, so their agreement is one observation reported twice — which is precisely
the error `independent_support()` exists to catch between witnesses, committed
one layer up between readers. A comparison of this project against
`epistemic-swarm` (see compare.md §8) found that gap; that project refuses an
overlapping roster at its configuration boundary, and so does this one now.

What "family" means, and the limits of the heuristic, are documented once in
`cohort.families`, which this module and `Graph.attest()` share. This check
guards the roster when a run is assembled; the write boundary guards the write
itself, and catches the case a roster cannot see — agents registered by
separate runs writing to one graph.
"""
from __future__ import annotations

from collections import defaultdict

from cohort.families import model_family

__all__ = ["RosterNotIndependent", "check_distinct_model_families", "model_family"]


class RosterNotIndependent(ValueError):
    """Two or more agents in one run share a model family."""


def check_distinct_model_families(models_by_agent: dict[str, str]) -> None:
    """Raise if two agents in the same run share a model family.

    A single-agent run is always fine: with nothing to agree with, shared
    priors cannot manufacture corroboration.
    """
    if len(models_by_agent) < 2:
        return
    families: dict[str, list[str]] = defaultdict(list)
    for agent_id, model in models_by_agent.items():
        families[model_family(model)].append(agent_id)

    clashes = {fam: ids for fam, ids in families.items() if len(ids) > 1}
    if not clashes:
        return
    detail = "; ".join(
        f"{', '.join(sorted(ids))} all use model family {fam!r}"
        for fam, ids in sorted(clashes.items())
    )
    raise RosterNotIndependent(
        f"agents in one run must not share a model family, and {detail}. "
        "Two agents on one model share training priors, so their agreement "
        "would be one observation reported twice — the error this system "
        "exists to catch between witnesses. Give each agent its own model "
        "(OPENROUTER_MODELS lists the pool), or run them as separate runs if "
        "they are dividing labour rather than offering competing readings."
    )
