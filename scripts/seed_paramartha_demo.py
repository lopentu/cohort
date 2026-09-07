"""Seed a graph for the Paramārtha (真諦) ascription question.

Manual only — never run by the test suite. Needs `data/radich/`.

**On the honesty of this demo.** The candidate list below is a fixed set of
discourse particles and connectives chosen for being register markers rather
than doctrinal vocabulary, and every one of them is registered here whether it
works or not. The prediction is the *same* for all of them — at least 60% of
measurable benchmark works, at most 20% of measurable control works — decided
once, in advance, rather than tuned per feature.

That matters because the numbers were seen before this script was written: a
scan over these candidates is what showed 復次 separating cleanly. Registering
only the winner would have produced a ledger reading "1 of 1 survived", which
would be true and deeply misleading. Registering all of them, against one
uniform threshold, is what makes the ratio mean something — and the ratio is
the only thing here that speaks to whether a survivor is a discovery or an
artefact of having looked twenty-two times.

A survivor is still not a Paramārtha marker. It is a feature that survived one
small negative control, on a corpus where the benchmark is 59% two Abhidharma
commentaries, and it may be tracking genre.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cohort.delta_study import open_study                         # noqa: E402
from cohort.catalogue import load_catalogue                       # noqa: E402
from cohort.eventlog import EventLog                              # noqa: E402
from cohort.graph import Graph                                    # noqa: E402
from cohort.ledger import ledger_json                             # noqa: E402
from cohort.schemas import (                                      # noqa: E402
    RESEARCHER,
    ConjecturePayload,
    EdgeType,
    QuestionPayload,
)
from cohort.sources.radich_reader import RadichReader             # noqa: E402
from cohort.tools.associate_work import (                         # noqa: E402
    AssociateWorkInput,
    associate_work,
)
from cohort.tools.discriminator import (                          # noqa: E402
    RegisterDiscriminatorInput,
    apply_to_disputed,
    register_discriminator,
    run_control_test,
)

DB = REPO_ROOT / "paramartha_demo.sqlite"
LOG = REPO_ROOT / "paramartha_demo.jsonl"
CORPUS = REPO_ROOT / "data" / "radich" / "corpus" / "T-stripped"
CATALOGUE = REPO_ROOT / "data" / "radich" / "P-catalogue.txt"

AGENT = "agent:stylometry-1"

#: Fixed before any of them was measured against the control, and registered
#: in full. Discourse particles and connectives: the register a translator
#: works in, rather than the subject matter a text happens to be about —
#: which is why 阿黎耶識 is *not* here. It is a fine marker of Yogācāra
#: content and a poor marker of anyone's hand.
CANDIDATES = [
    "復次", "為顯", "能取", "所取", "譬如", "即是", "由此", "亦爾",
    "此中", "應知", "不然", "若爾", "無有", "是故", "如是", "何以故",
    "云何", "義故", "有二", "所以者何", "第一義", "非有",
]

MIN_BENCHMARK_SHARE = 0.60
MAX_CONTROL_SHARE = 0.20


def main() -> None:
    if not CORPUS.is_dir():
        raise SystemExit(f"no corpus at {CORPUS} — see data/PROVENANCE.md")
    for stale in (DB, LOG, Path(str(DB) + ".lock")):
        stale.unlink(missing_ok=True)

    catalogue = load_catalogue(
        CATALOGUE, benchmark_label="P-23", control_label="interloper",
    )
    corpus = RadichReader(CORPUS, works=catalogue.works())
    catalogue.check_against(corpus.works())
    graph = Graph(DB, event_log=EventLog(LOG))

    question_id = graph.ask_question(
        QuestionPayload(
            text=(
                "Which of the P-weird works can be placed with or apart from "
                "the P-23 benchmark for Paramārtha's translation idiom?"
            ),
            answerable_by=(
                "feature counts over the Radich Taishō corpus as catalogued: "
                "they can show that a feature does or does not separate the "
                "benchmark from a control, and where a disputed work falls on "
                "it. They cannot establish authorship, and cannot speak to "
                "works below the character floor."
            ),
        ),
        authored_by=RESEARCHER,
    )

    print(f"registering {len(CANDIDATES)} candidates at "
          f">={MIN_BENCHMARK_SHARE:.0%} benchmark / <={MAX_CONTROL_SHARE:.0%} control\n")
    survivors = []
    for feature in CANDIDATES:
        out = register_discriminator(
            graph,
            RegisterDiscriminatorInput(
                feature=feature,
                min_benchmark_share=MIN_BENCHMARK_SHARE,
                max_control_share=MAX_CONTROL_SHARE,
                derivation=(
                    f"{feature} is a discourse particle or connective rather "
                    "than doctrinal vocabulary, so it is a candidate for "
                    "tracking a translator's register rather than a text's "
                    "subject matter."
                ),
                corpus_boundary=(
                    "Radich Taishō corpus (CC-BY-4.0), P-catalogue works only, "
                    "base edition 大, works under 5,000 characters not rated."
                ),
                selection_risks=(
                    "The candidate list was fixed by hand from a reading of "
                    "which forms are register-bearing, not sampled; and the "
                    "P-23 benchmark is 59% two Abhidharma commentaries by "
                    "character count, so a feature may separate on genre."
                ),
                alternative_explanations=(
                    "A separating feature may track genre, date, or the "
                    "editorial habits of one recension rather than the "
                    "translator; the control contains only four works, and "
                    "only three are long enough to measure."
                ),
            ),
            catalogue=catalogue, authored_by=AGENT,
        )
        res = run_control_test(
            graph, corpus, out["conjecture_id"], catalogue=catalogue, authored_by=AGENT,
        )
        b, c = res["benchmark"], res["control"]
        mark = "survived " if str(res["result"]) == "pass" else "discarded"
        print(f"  {mark}  {feature:<10} benchmark {b.works_attesting}/{b.works_measured}"
              f"  control {c.works_attesting}/{c.works_measured}")
        if str(res["result"]) == "pass":
            survivors.append((feature, out["conjecture_id"]))

    print()
    for feature, cid in survivors:
        # Authored, so the rows land in the graph rather than only in this
        # printout. Which works in doubt a surviving feature places where is
        # the one concrete output of the whole method, and it used to reach
        # stdout and nothing else — invisible to the Findings page that is
        # supposed to be where the result is read.
        applied = apply_to_disputed(
            graph, corpus, cid, catalogue=catalogue, disputed_label="P-weird",
            authored_by=AGENT,
        )
        placed = [r["work"] for r in applied["works"] if r["attests"]]
        silent = [r["work"] for r in applied["works"] if r["attests"] is False]
        unmeasurable = [r["work"] for r in applied["works"] if r["attests"] is None]
        print(f"  {feature}: with benchmark {placed or '—'}; without {silent or '—'}"
              + (f"; too short {unmeasurable}" if unmeasurable else ""))

    # --- association: the question Radich actually asked ---------------------
    #
    # The feature ledger above answers "which candidate features separate the
    # benchmark from a control". That is a prerequisite, not the brief. The
    # brief asks whether a P-weird work can be associated with P *against texts
    # by other translators in the canon*, or associated with some other
    # reference point suggesting an alternate ascription — a question about
    # 1,464 profiled works, not about three measurable interlopers.
    #
    # One conjecture per work, phrased as the open question rather than as its
    # answer, with the measurement recorded against it. A conjecture is allowed
    # to exceed its evidence; what it may not do is state the finding in its own
    # text and then be "confirmed" by a number computed afterwards.
    print("\nbuilding the Delta space over the whole canon — about 60s, once")
    study = open_study(REPO_ROOT / "data" / "radich")
    print(f"  {study.corpus_size} works read, {len(study.space.works())} profiled")
    cal = study.calibration()[25]
    print(f"  calibration: a known {catalogue.benchmark_label} work reaches "
          f"{cal.minimum:.0%}–{cal.maximum:.0%} (median {cal.median:.0%}); "
          f"{cal.blind} of {cal.n} score zero\n")

    for work in catalogue.works("P-weird"):
        if work not in study.space.works():
            print(f"  {work:<10} below the character floor — not profiled")
            continue
        cid = graph.propose_conjecture(
            ConjecturePayload(
                text=(
                    f"{work} can be associated with {catalogue.benchmark_label} "
                    "rather than with some other reference point in the canon."
                ),
                derivation=(
                    "Burrows's Delta over the 300 most frequent character "
                    "bigrams, computed across the whole Taisho corpus so that "
                    "the comparison set is every profiled work rather than the "
                    "catalogue. The question is whether "
                    f"{catalogue.benchmark_label} members are over-represented "
                    "among this work's nearest neighbours."
                ),
                corpus_boundary=(
                    "Radich Taisho corpus (CC-BY-4.0), one edition per work "
                    "(大), works under 5,000 characters not profiled."
                ),
                selection_risks=(
                    "The benchmark is 59% two Abhidharma commentaries by "
                    "character count, so its centroid sits in that genre and a "
                    "work of the same genre may be drawn to it whoever "
                    "translated it."
                ),
                alternative_explanations=(
                    "Character n-grams track subject matter heavily. A "
                    "neighbourhood is evidence about resemblance rather than "
                    "authorship, and the measure reports the nearest work "
                    "outside the group precisely so that this can be checked."
                ),
            ),
            authored_by=AGENT,
        )
        graph.add_edge(EdgeType.ADDRESSES, cid, question_id, authored_by=AGENT)
        out = associate_work(
            graph, study,
            AssociateWorkInput(claim_or_conjecture_id=cid, work=work),
            authored_by=AGENT,
        )
        a = out["association"]
        e, h = a["enrichment"][0], a["neighbourhood"]
        # Both branches on one line. The verdict comes from the record rather
        # than being re-derived here, so this printout cannot disagree with
        # what the graph says.
        print(f"  {a['verdict']:<10} {work:<10} "
              f"{e['hits']:>2}/{e['k']} {catalogue.benchmark_label} "
              f"(p={e['p_value']:.0e})   nearest {h['nearest']['work']} "
              f"Δ{h['nearest_delta']} gap {h['gap_to_second']} "
              f"[{h['gap_percentile']:.0f}th pct"
              + (", dominant]" if h["dominant"] else
                 ", diffuse]" if h["diffuse"] else "]"))

    led = ledger_json(graph)
    print(f"\n{led['reading']}")
    print(f"\nseeded {DB.name}. Serve it with:")
    print(f"  .venv/bin/python scripts/serve_ui.py --db {DB.name} "
          "--allow-writes --corpus --allow-runs --max-budget 0.50 --port 8000")
    corpus.close()
    graph.close()


if __name__ == "__main__":
    main()
