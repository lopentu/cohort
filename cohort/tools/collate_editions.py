"""collate_editions: record what a witness's TEI apparatus says about which
editions support its text, as a `CROSS_EDITION_COLLATION` verification
(build order stage 4).

The evidence is `<app>`/`<lem>`/`<rdg>` markup, which is pervasive in CBETA
v061 (an `<app>` citing two or more distinct editions appears in roughly nine
of ten entries by sampling). `cohort/sources/cbeta_markup.py` reads it; this
tool records a judgement about it.

**What this verification does and does not establish.** It reports the
edition support behind a witness's text — which editions were collated, where
the adopted reading is a modern editorial emendation rather than an inherited
one. It does *not* establish that two witnesses in the graph are independent
of each other: apparatus describes variants *within one document*, so it
cannot speak to the relation between two different Taisho texts. That relation
comes from `parallel_of`/`descends_from` edges (see
`cohort/tools/link_parallels.py`) and is read by
`Graph.independent_support()`.

The rung it earns says this now. It was `A3_INDEPENDENCE_CHECKED` until
2026-09-02, and this docstring and the `limitations` on every record existed
partly to talk a reader *out* of the label the tool was obliged to apply —
which was a misnamed rung rather than a careful tool. `A3_EDITION_SUPPORT_CHECKED`
names what is actually checked. The `limitations` text stays, because the
boundary is worth stating on each record, but it is now information rather
than a disclaimer against the tool's own grade.

**Joint sigla are never split.** `wit="【宋】 【元】 【明】 【宮】"` is one
shared-descent family reading one way, not four independent confirmations;
counting it as four is precisely the error docs/design.md §4 is about. The tally
`cohort.sources.cbeta_markup.edition_families()` returns is therefore keyed by
the group as written, and this tool reports it that way.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cohort.errors import WrongNodeType
from cohort.graph import Graph
from cohort.schemas import AssuranceLevel, NodeType, VerificationMethod, VerificationResult
from cohort.sources.base import Source
from cohort.sources.cbeta_markup import edition_families, parse_apparatus

from ._witness_source import source_ref_for_witness

NAME = "collate_editions"
DESCRIPTION = (
    "Record a cross_edition_collation verification for a witness, reporting "
    "which edition families its TEI apparatus cites and whether its adopted "
    "readings include modern editorial emendations."
)

#: sigla and `resp` values that mark a reading as a modern editorial
#: judgement rather than one inherited from a manuscript witness.
_EDITORIAL_SIGLUM_PREFIX = "【CB"


class CollateEditionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    witness_id: str = Field(min_length=1)


def collate_editions(
    graph: Graph, source: Source, args: CollateEditionsInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> str:
    witness = graph.get_node(args.witness_id)
    if witness.type != NodeType.WITNESS:
        raise WrongNodeType(f"{args.witness_id} is a {witness.type}, not a witness")

    source_ref = source_ref_for_witness(graph, args.witness_id)
    if source_ref is None:
        return graph.verify(
            args.witness_id, method=VerificationMethod.CROSS_EDITION_COLLATION,
            result=VerificationResult.INDETERMINATE,
            assurance_level=AssuranceLevel.A0_UNCHECKED,
            detail=(
                "no passage of this witness carries a source_ref, so its document "
                "could not be re-fetched; no apparatus was read"
            ),
            authored_by=authored_by, model_call_id=model_call_id,
        )

    document = source.fetch(source_ref).text
    entries = parse_apparatus(document)

    if not entries:
        return graph.verify(
            args.witness_id, method=VerificationMethod.CROSS_EDITION_COLLATION,
            result=VerificationResult.INDETERMINATE,
            assurance_level=AssuranceLevel.A0_UNCHECKED,
            detail="document carries no <app> apparatus; there is no collation evidence to read",
            limitations=_LIMITATIONS,
            authored_by=authored_by, model_call_id=model_call_id,
        )

    families = edition_families(entries)
    editorial = [
        e.n for e in entries
        if e.lemma is not None and (
            any(s.startswith(_EDITORIAL_SIGLUM_PREFIX) for s in e.lemma.sigla)
            or (e.lemma.resp or "").upper().startswith("CBETA")
        )
    ]
    joint = sorted(k for k in families if len(k.split()) > 1)

    detail = (
        f"{len(entries)} apparatus entries; edition groups cited (as written, "
        f"joint groups not split): "
        + "; ".join(f"{group} x{count}" for group, count in
                    sorted(families.items(), key=lambda kv: (-kv[1], kv[0])))
    )
    if joint:
        detail += f". Joint (shared-descent) groups: {', '.join(joint)}"
    if editorial:
        shown = ", ".join(str(n) for n in editorial[:8] if n)
        detail += (
            f". {len(editorial)} adopted reading(s) are modern editorial emendations"
            + (f" (e.g. app n={shown})" if shown else "")
        )

    return graph.verify(
        args.witness_id, method=VerificationMethod.CROSS_EDITION_COLLATION,
        result=VerificationResult.PASS,
        assurance_level=AssuranceLevel.A3_EDITION_SUPPORT_CHECKED,
        detail=detail, limitations=_LIMITATIONS,
        authored_by=authored_by, model_call_id=model_call_id,
    )


_LIMITATIONS = (
    "Records edition support for this witness's own text only. Apparatus "
    "describes variants within a single document, so it says nothing about "
    "whether this witness is independent of any other witness in the graph — "
    "that relation is carried by parallel_of/descends_from edges and read by "
    "independent_support(). Joint sigla are reported as single shared-descent "
    "families and must not be counted as separate confirmations."
)


