"""Translator-attribution evidence over Radich's pre-450 Taishō corpus.

Radich labels ~1,400 units of text (whole short works, or chapters of long
ones) with the translator whose ascription is secure, and quarantines ~970 as
`grey`. His question 1: can anything help determine who the grey ones belong
to? This module does the one thing a machine can honestly do here: it counts.

For a chosen text it reports, per short string (2-4 characters), how much more
often that string appears in translator A's securely ascribed work than in
translator B's, sums those weights over the text, and hands back the spans and
the strings so a reader can look at them. It names a leaning, never a verdict,
and when there is nothing to count it says so instead of naming anyone.

Four rules keep the numbers honest, each learned the hard way:

* **A text is never judged against its own book.** Long works are split into
  chapters, all labelled alike. Recognising chapter 40 of T26 from chapters
  1-39 is recognising the book, not the translator, and it inflated accuracy
  from 52% to 82% before it was caught. So when the target is labelled, every
  unit of the same Taishō work is withheld from the profiles first.
* **Two feature vocabularies, because one of them is biased.** Radich's Table 1
  lists strings he harvested for a Dharmarakṣa dictionary. As attribution
  features they see Dharmarakṣa well and the earliest translators barely at
  all. The `generic` set is the commonest strings in the *grey* texts: a corpus
  of the same period that is never evaluated on, so no held-out work can shape
  the features and no label is read. Showing both is how the bias becomes
  visible instead of confessed.
* **Everything discarded is counted.** Units under the length floor, classes
  too small to profile, directories with no text: the ledger says how many and
  why, because a number you cannot see is a number you cannot defend.
* **Every answer says where it came from.** Dataset folder, file hashes,
  vocabulary source and code version travel with each result, so a coloured
  span can be traced to the bytes that produced it.

Standard library only. Nothing is trained; a profile is a table of counts.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import pickle
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cohort.sources.cbeta_refs import unit_reader_url

CATALOGUE = "DhR tables FULL catalogue.txt"
MARKERS = "Table 1 XML CANONICAL.xml"
CORPUS_DIR = Path("corpus") / "T-stripped"
#: Base-text filenames, in order of preference. Radich's corpus carries the
#: Taishō text plus each edition's variants; the Taishō file is the reading
#: everyone cites.
EDITIONS = ("大.txt", "CB.txt", "麗-CB.txt")

MIN_CHARS = 2000  #: shorter units carry too few strings to profile
MIN_UNITS = 5  #: a class with fewer labelled units is not a profile
MIN_MARKERS = 1000  #: fewer parsed <ngram> entries means Table 1 did not load
LOW_EVIDENCE = 10  #: fewer distinct strings than this and the leaning is flagged
NGRAM_LENGTHS = (2, 3, 4)
WINDOW = 400  #: characters per cell of the whole-text strip
MAX_CELLS = 600  #: the strip widens its cells rather than exceed this
EXCERPT = 2400  #: characters painted individually
FEATURE_SETS = ("radich", "generic", "both")
#: Bumped whenever the counting changes, so a cache built by older code is
#: rebuilt rather than trusted: the fingerprint covers inputs *and* method.
CODE_VERSION = 3
GREY = "grey"
CACHE_NAME = ".cohort-attribution"
#: Singletons are pruned from the running n-gram table once it grows past this;
#: a string seen once corpus-wide is nowhere near the top few thousand.
PRUNE_AT = 3_000_000

#: A Taishō number is exactly four digits; the lookahead stops `T06030` from
#: silently mapping to `T0603` while still accepting `T0150A-12`.
_WORK = re.compile(r"T\d{4}(?!\d)")
#: Han script: Extension A, the unified block, the compatibility block, and the
#: supplementary-plane extensions B-F. Radich's corpus uses all of them; the
#: first version of this predicate covered only the unified block and made two
#: pipelines disagree on An Shigao by four units out of eleven.
_HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)


def work_of(uid: str) -> str:
    """Return the Taishō work a unit belongs to: `T0150A-12` -> `T0150`.

    Units of one work share a source text and a translation session, which is
    why they are withheld together.
    """
    m = _WORK.match(uid)
    if m is None:
        msg = f"unit id {uid!r} does not start with a Taishō number"
        raise ValueError(msg)
    return m.group(0)


def is_han(ch: str) -> bool:
    """Return True for a Han (CJK ideograph) character in any of the blocks used here."""
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in _HAN_RANGES)


def han_count(text: str) -> int:
    """Return the number of Han characters in `text` (punctuation and breaks excluded)."""
    return sum(1 for ch in text if is_han(ch))


def read_catalogue(path: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """Return `unit id -> label`, the block order, and notes on the file's irregularities.

    The block order is the only place Radich's historical sequence lives. The
    file is CRLF and blank-line delimited, one label per block by intent. One
    block is not (a stray `grey` line sits inside the Dharmarakṣa block), so a
    block's label is its majority and the exception is reported rather than
    silently shifting every later block by one.
    """
    raw = path.read_bytes()
    if b"\r\n" not in raw:
        msg = f"{path.name}: expected CRLF line endings; has the file been rewritten?"
        raise ValueError(msg)
    text = raw.decode("utf-8").replace("\r", "")
    labels: dict[str, str] = {}
    order: list[str] = []
    notes: list[str] = []
    for block in (b for b in text.split("\n\n") if b.strip()):
        rows = [ln.split() for ln in block.strip().split("\n") if ln.split()]
        if any(len(r) < 2 for r in rows):
            msg = f"{path.name}: a catalogue line has no label"
            raise ValueError(msg)
        here = collections.Counter(r[-1] for r in rows)
        majority, _ = here.most_common(1)[0]
        if len(here) > 1:
            strays = ", ".join(f"{n} line(s) labelled {lab}" for lab, n in here.items() if lab != majority)
            notes.append(f"the {majority} block also contains {strays}; the block keeps its majority label")
        order.append(majority)
        for r in rows:
            labels[r[0]] = r[-1]
    if len(order) != len(set(order)):
        msg = f"{path.name}: a label owns two blocks; the sequence is ambiguous"
        raise ValueError(msg)
    return labels, [lab for lab in order if lab != GREY], notes


def read_markers(path: Path) -> set[str]:
    """Return Radich's curated strings of 2-4 characters (96% of his list)."""
    xml = path.read_text(encoding="utf-8")
    marks = {g for g in re.findall(r"<ngram>(.*?)</ngram>", xml) if len(g) in NGRAM_LENGTHS}
    if len(marks) < MIN_MARKERS:
        msg = f"{path.name}: only {len(marks)} <ngram> entries parsed"
        raise ValueError(msg)
    return marks


def ngrams(text: str) -> collections.Counter:
    """Count every 2/3/4-character string in the text.

    No character filter here: the vocabulary decides what counts, so Radich's
    markers with supplementary-plane characters are counted like the rest.
    """
    seen: collections.Counter = collections.Counter()
    for n in NGRAM_LENGTHS:
        seen.update(text[i : i + n] for i in range(len(text) - n + 1))
    return seen


def commonest(texts: Iterable[str], shape: dict[int, int]) -> set[str]:
    """Return the top-k commonest all-Han strings per length across `texts`.

    `shape` gives k per length so the result matches another feature set in
    size and length mix. Reads no labels.
    """
    texts = list(texts)
    out: set[str] = set()
    for n, k in sorted(shape.items()):
        c: collections.Counter = collections.Counter()
        for i, t in enumerate(texts, 1):
            c.update(
                g for g in (t[j : j + n] for j in range(len(t) - n + 1)) if all(is_han(ch) for ch in g)
            )
            if i % 25 == 0 and len(c) > PRUNE_AT:
                for g in [g for g, v in c.items() if v == 1]:
                    del c[g]
        take = [g for g, _ in c.most_common(k)]
        if len(take) < k:
            msg = f"only {len(take)} distinct {n}-grams in the corpus; wanted {k}"
            raise ValueError(msg)
        out.update(take)
    return out


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class _Index:
    """What `AttributionIndex.load` computes once and caches beside the data."""

    labels: dict[str, str]
    sequence: list[str]
    notes: list[str]
    ledger: dict[str, int]
    features: dict[str, set[str]]
    #: feature set -> unit -> its counts restricted to that set
    counts: dict[str, dict[str, collections.Counter]]
    unit_label: dict[str, str]  #: the kept labelled units only
    han_chars: dict[str, int]  #: Han length of every unit with a base text
    members: dict[str, list[str]] = field(default_factory=dict)  #: work -> kept units
    file_hashes: dict[str, str] = field(default_factory=dict)  #: relative path -> sha256

    def members_of(self, label: str) -> list[str]:
        return [u for u, lab in self.unit_label.items() if lab == label]


class AttributionIndex:
    """Radich's corpus, profiled and ready to answer for one text at a time.

    `load` does the counting (a minute or two) and caches the result, keyed by
    a content hash of every input file plus the code version, so a server
    restart is instant and a changed file or a changed method is noticed.
    """

    def __init__(self, root: Path, index: _Index) -> None:
        self.root = Path(root)
        self._ix = index

    # ------------------------------------------------------------ loading --
    @classmethod
    def load(cls, root: str | Path, *, use_cache: bool = True) -> AttributionIndex:
        """Build the index, or read it back from a cache whose key still matches."""
        root = Path(root)
        for name in (CATALOGUE, MARKERS):
            if not (root / name).is_file():
                msg = f"{root / name}: the Radich data folder needs this file"
                raise FileNotFoundError(msg)
        if not (root / CORPUS_DIR).is_dir():
            msg = f"{root / CORPUS_DIR}: no corpus directory"
            raise FileNotFoundError(msg)
        hashes = cls._hash_inputs(root)
        key = cls._fingerprint(hashes)
        cache = cls._cache_path(root)
        if use_cache:
            index = cls._read_cache(cache, key)
            if index is not None:
                return cls(root, index)
        index = cls._build(root, hashes)
        if use_cache:
            cls._write_cache(cache, key, index)
        return cls(root, index)

    @staticmethod
    def _hash_inputs(root: Path) -> dict[str, str]:
        """Return sha256 of every input file, keyed by path relative to `root`.

        Empty unit directories and directories with no base text are recorded
        too (with an empty hash), so a directory appearing or emptying changes
        the key even though no file bytes changed.
        """
        hashes = {name: _sha256((root / name).read_bytes()) for name in (CATALOGUE, MARKERS)}
        for d in sorted(p for p in (root / CORPUS_DIR).iterdir() if p.is_dir()):
            for ed in EDITIONS:
                if (d / ed).is_file():
                    hashes[f"{CORPUS_DIR}/{d.name}/{ed}"] = _sha256((d / ed).read_bytes())
                    break
            else:
                hashes[f"{CORPUS_DIR}/{d.name}/"] = ""
        return hashes

    @staticmethod
    def _fingerprint(hashes: dict[str, str]) -> str:
        # The method is part of the key: every constant that changes a count
        # is hashed, so forgetting to bump CODE_VERSION cannot serve stale profiles.
        method = (
            f"code-version:{CODE_VERSION} min-chars:{MIN_CHARS} min-units:{MIN_UNITS} "
            f"ngrams:{NGRAM_LENGTHS} editions:{EDITIONS} window:{WINDOW} "
            f"max-cells:{MAX_CELLS} excerpt:{EXCERPT} low-evidence:{LOW_EVIDENCE} "
            f"prune:{PRUNE_AT} features:{FEATURE_SETS}\n"
        )
        h = hashlib.sha256(method.encode())
        for name in sorted(hashes):
            h.update(f"{name}:{hashes[name]}\n".encode())
        return h.hexdigest()

    @staticmethod
    def _cache_path(root: Path) -> Path:
        """Cache beside the data when that folder is writable, else under the user's cache dir."""
        if os.access(root, os.W_OK):
            return root / f"{CACHE_NAME}.pkl"
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "cohort"
        return base / f"{CACHE_NAME}-{_sha256(str(root.resolve()).encode())[:12]}.pkl"

    @staticmethod
    def _read_cache(cache: Path, key: str) -> _Index | None:
        """Read the cache only if its sidecar key matches; anything malformed means rebuild.

        A pickle, deliberately: it is a cache this process wrote itself, and it
        is only unpickled after the key file beside it says it was built from
        exactly these inputs by exactly this code. Nothing from the network or
        another party is ever unpickled here.
        """
        keyfile = cache.with_suffix(".key")
        if not (cache.is_file() and keyfile.is_file()):
            return None
        try:
            if json.loads(keyfile.read_text(encoding="utf-8")).get("key") != key:
                return None
            with cache.open("rb") as fh:
                index = pickle.load(fh)
        except (OSError, ValueError, pickle.UnpicklingError, EOFError, AttributeError):
            return None
        return index if isinstance(index, _Index) else None

    @staticmethod
    def _write_cache(cache: Path, key: str, index: _Index) -> None:
        """Write atomically: a reader never sees a half-written pickle or a key without its data."""
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=cache.parent, prefix=cache.name, suffix=".tmp")
            with os.fdopen(fd, "wb") as fh:
                pickle.dump(index, fh)
            os.replace(tmp, cache)
            keyfile = cache.with_suffix(".key")
            keyfile.write_text(json.dumps({"key": key, "code_version": CODE_VERSION}), encoding="utf-8")
        except OSError:
            # The cache is a convenience; an unwritable folder must not stop the answer.
            return

    @staticmethod
    def base_text(root: Path, uid: str) -> str | None:
        """Return the unit's Taishō base text, or None when the corpus has none."""
        d = root / CORPUS_DIR / uid
        if not d.is_dir():
            return None
        for ed in EDITIONS:
            p = d / ed
            if p.is_file():
                return p.read_text(encoding="utf-8")
        return None

    @staticmethod
    def base_file(root: Path, uid: str) -> Path | None:
        """Return the path of the unit's base text, or None."""
        d = root / CORPUS_DIR / uid
        for ed in EDITIONS:
            if (d / ed).is_file():
                return d / ed
        return None

    @classmethod
    def _build(cls, root: Path, hashes: dict[str, str]) -> _Index:
        labels, sequence, notes = read_catalogue(root / CATALOGUE)
        marks = read_markers(root / MARKERS)
        ledger: collections.Counter[str] = collections.Counter()
        ledger["catalogue units, non-grey"] = sum(1 for lab in labels.values() if lab != GREY)
        ledger["catalogue units, grey"] = sum(1 for lab in labels.values() if lab == GREY)

        texts: dict[str, str] = {}
        grey_texts: list[str] = []
        han_chars: dict[str, int] = {}
        for uid, label in labels.items():
            t = cls.base_text(root, uid)
            if t is None:
                # Split by grey/non-grey so the non-grey rows add up to the
                # kept count: a ledger that does not sum is not a ledger.
                who = "grey" if label == GREY else "non-grey"
                if (root / CORPUS_DIR / uid).is_dir():
                    ledger[f"dropped ({who}): directory has no base text"] += 1
                else:
                    ledger[f"dropped ({who}): no such directory"] += 1
                continue
            han_chars[uid] = han_count(t)
            if label == GREY:
                grey_texts.append(t)
                continue
            if han_chars[uid] < MIN_CHARS:
                ledger[f"dropped: under the {MIN_CHARS:,}-character floor"] += 1
                continue
            texts[uid] = t

        per_class = collections.Counter(labels[u] for u in texts)
        keep = {lab for lab, n in per_class.items() if n >= MIN_UNITS}
        for lab, n in sorted(per_class.items()):
            if lab not in keep:
                ledger[f"dropped: class too small to profile ({lab}, {n} units)"] += n
        texts = {u: t for u, t in texts.items() if labels[u] in keep}
        ledger["kept for profiling"] = len(texts)
        ledger["classes profiled"] = len(keep)

        shape = collections.Counter(len(m) for m in marks)
        # Drawn from the grey texts: never evaluated on, so never a leak. A
        # corpus with no grey text has nothing safe to draw from; refusing is
        # better than quietly selecting on the texts we then evaluate.
        if not grey_texts:
            msg = "no grey texts to draw the label-free vocabulary from"
            raise ValueError(msg)
        generic = commonest(grey_texts, shape)
        features = {"radich": marks, "generic": generic, "both": marks | generic}
        ledger["features: radich"] = len(marks)
        ledger["features: generic"] = len(generic)
        ledger["features: shared by both"] = len(marks & generic)
        ledger["grey texts the generic vocabulary was drawn from"] = len(grey_texts)

        counts: dict[str, dict[str, collections.Counter]] = {k: {} for k in features}
        members: dict[str, list[str]] = collections.defaultdict(list)
        for uid, t in texts.items():
            seen = ngrams(t)
            for name, fs in features.items():
                counts[name][uid] = collections.Counter({g: c for g, c in seen.items() if g in fs})
            members[work_of(uid)].append(uid)

        return _Index(
            labels=labels,
            sequence=sequence,
            notes=notes,
            ledger=dict(ledger),
            features=features,
            counts=counts,
            unit_label={u: labels[u] for u in texts},
            han_chars=han_chars,
            members=dict(members),
            file_hashes=hashes,
        )

    # ------------------------------------------------------------ queries --
    def units(self) -> dict[str, Any]:
        """List every unit that has a base text, with the ledger and the class sequence."""
        ix = self._ix
        rows = [
            {"uid": u, "label": ix.labels[u], "han_chars": n, "profiled": u in ix.unit_label}
            for u, n in ix.han_chars.items()
        ]
        return {
            "units": rows,
            "sequence": ix.sequence,
            "classes": sorted({ix.labels[u] for u in ix.unit_label}),
            "feature_sets": list(FEATURE_SETS),
            "ledger": ix.ledger,
            "notes": ix.notes,
            "provenance": self._provenance(),
        }

    def _provenance(self, uid: str | None = None) -> dict[str, Any]:
        """Say exactly which bytes an answer came from."""
        ix = self._ix
        out: dict[str, Any] = {
            "dataset": str(self.root),
            "catalogue": {"file": CATALOGUE, "sha256": ix.file_hashes.get(CATALOGUE)},
            "markers": {"file": MARKERS, "sha256": ix.file_hashes.get(MARKERS)},
            "generic_vocabulary": "commonest all-Han 2/3/4-grams of the grey texts, "
            "matched to Table 1 in size and length mix; no label read",
            "code_version": CODE_VERSION,
        }
        if uid is not None:
            f = self.base_file(self.root, uid)
            rel = f"{CORPUS_DIR}/{uid}/{f.name}" if f else None
            out["base_text"] = {"file": rel, "sha256": ix.file_hashes.get(rel or "", None)}
        return out

    def evidence(
        self,
        uid: str,
        features: str = "radich",
        *,
        withhold: Iterable[str] = (),
        offset: int = 0,
        pair: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return where a text leans, and the strings and spans that make it lean.

        The ranking runs over every profiled class. The *painting* compares two
        of them, `pair` = (A, B): teal pulls toward A, rust toward B. By default
        A is the text's own catalogue label when that label is profiled (so a
        labelled text is always painted "for its translator vs the strongest
        rival"), otherwise the leader; B is the strongest other class. Pinning
        the pair is what makes the colours mean the same thing across
        vocabularies: without it, teal would simply be whoever is winning.

        `withhold` names further profiled units to remove from the profiles
        beyond the target's own work: the sensitivity test a reader runs when
        they suspect one text is quoting another. `offset` chooses which
        `EXCERPT` characters are painted individually.
        """
        ix = self._ix
        if features not in FEATURE_SETS:
            msg = f"features must be one of {FEATURE_SETS}, not {features!r}"
            raise ValueError(msg)
        if uid not in ix.labels:
            msg = f"{uid} is not in the catalogue"
            raise KeyError(msg)
        text = self.base_text(self.root, uid)
        if text is None:
            msg = f"{uid} has no base text in the corpus"
            raise KeyError(msg)
        offset = max(0, min(int(offset), max(len(text) - 1, 0)))
        fs = ix.features[features]
        vocab = len(fs)
        label = ix.labels[uid]

        # Profiles, minus every profiled unit of the target's own work (the
        # target itself included) and anything the caller asked to withhold.
        extra = set(withhold)
        unknown = sorted(u for u in extra if u not in ix.unit_label)
        if unknown:
            msg = f"cannot withhold units that are not profiled: {unknown}"
            raise ValueError(msg)
        withheld = set(ix.members.get(work_of(uid), [])) | extra
        profiles: dict[str, collections.Counter] = {lab: collections.Counter() for lab in set(ix.unit_label.values())}
        remaining_units: collections.Counter[str] = collections.Counter()
        for u, lab in ix.unit_label.items():
            if u not in withheld:
                remaining_units[lab] += 1
                profiles[lab].update(ix.counts[features][u])
        # A translator cannot be judged under this vocabulary if nothing of
        # theirs is left, or if what is left has no hits at all. Smoothing
        # would rank them anyway (a flat distribution scores as well as a thin
        # real one), so they are named as unjudged rather than silently ranked.
        no_profile = [
            {"label": lab, "reason": "no units left after withholding" if remaining_units[lab] == 0 else "no hits in this vocabulary"}
            for lab, p in sorted(profiles.items())
            if not p
        ]
        profiles = {lab: p for lab, p in profiles.items() if p}
        if len(profiles) < 2:
            msg = "fewer than two classes have a profile left after withholding"
            raise ValueError(msg)
        # The leak this guards against cost 30 accuracy points once. The check
        # is on the invariant itself, not a re-run of the same arithmetic: no
        # unit that fed a profile may belong to the target's work or be one the
        # caller asked to withhold. (An earlier version recomputed the profile
        # from the same `withheld` set and compared: it could never fail.)
        contributors = [u for u in ix.unit_label if u not in withheld]
        leaked = [u for u in contributors if work_of(u) == work_of(uid) or u in extra]
        if leaked:
            msg = f"leak: profiles still contain {leaked[:3]} from the target's work or the withheld list"
            raise RuntimeError(msg)

        total = {lab: sum(p.values()) for lab, p in profiles.items()}
        smooth = {lab: total[lab] + 0.5 * vocab for lab in profiles}

        def logp(lab: str, g: str) -> float:
            return math.log((profiles[lab].get(g, 0) + 0.5) / smooth[lab])

        def per100k(lab: str, g: str) -> float:
            return 1e5 * profiles[lab].get(g, 0) / total[lab] if total[lab] else 0.0

        occ = [
            (i, text[i : i + n]) for n in NGRAM_LENGTHS for i in range(len(text) - n + 1) if text[i : i + n] in fs
        ]
        counts = collections.Counter(g for _, g in occ)
        result: dict[str, Any] = {
            "uid": uid,
            "cbeta_url": unit_reader_url(uid),
            "label": label,
            "work": work_of(uid),
            "features": features,
            "n_features": vocab,
            "code_points": len(text),
            "han_chars": ix.han_chars.get(uid, han_count(text)),
            "hits": len(occ),
            "distinct": len(counts),
            "withheld_units": len(withheld),
            "withheld_extra": sorted(extra),
            "no_profile": no_profile,
            "window": WINDOW,
            "provenance": self._provenance(uid),
            # Per class: what is left to judge by, and where the class sits in
            # Radich's historical order. `thin` marks a profile that fell under
            # the class minimum after withholding; a leaning toward or away
            # from a thin class rests on very little.
            "profiles": {
                lab: {
                    "units": remaining_units[lab],
                    "units_before_withholding": len(ix.members_of(lab)),
                    "feature_tokens": total[lab],
                    "thin": remaining_units[lab] < MIN_UNITS,
                    "sequence": ix.sequence.index(lab) if lab in ix.sequence else None,
                }
                for lab in sorted(profiles)
            },
        }

        # Nothing to count means nothing to say. Naming a leader from a tie of
        # zeros is how a method names a translator for a text nobody translated.
        if not counts:
            result.update(
                {
                    "verdict": "no evidence",
                    "first": None,
                    "second": None,
                    "margin": 0.0,
                    "gap": 0.0,
                    "pair": None,
                    "ranking": [],
                    "strip_cell": WINDOW,
                    "strip_scale": 1.0,
                    "strip": [{"start": s, "end": min(s + WINDOW, len(text)), "mean": 0.0} for s in range(0, len(text), WINDOW)],
                    "excerpt": {
                        "start": offset,
                        "end": min(offset + EXCERPT, len(text)),
                        "text": text[offset : offset + EXCERPT],
                        "evidence": [0.0] * len(text[offset : offset + EXCERPT]),
                    },
                    "scale": 1.0,
                    "for": [],
                    "against": [],
                }
            )
            return result

        score = {lab: sum(c * logp(lab, g) for g, c in counts.items()) for lab in profiles}
        ranked = sorted(score, key=lambda lab: score[lab], reverse=True)
        first, second = ranked[0], ranked[1]
        margin = (score[first] - score[second]) / len(counts)

        if pair is not None:
            a, b = pair
            bad = [lab for lab in (a, b) if lab not in profiles]
            if bad or a == b:
                msg = f"pair must name two distinct profiled classes; got {pair!r}"
                raise ValueError(msg)
        else:
            a = label if label in profiles else first
            b = next(lab for lab in ranked if lab != a)

        weight = {g: logp(a, g) - logp(b, g) for g in counts}
        ev = [0.0] * len(text)
        for i, g in occ:
            w = weight[g] / len(g)
            for k in range(len(g)):
                ev[i + k] += w
        nonzero = sorted(abs(e) for e in ev if e)
        scale = nonzero[int(0.95 * (len(nonzero) - 1))] if nonzero else 1.0

        # One cell per WINDOW characters, but never more than MAX_CELLS: a
        # 1.2-million-character work would otherwise ask for 3,000 one-pixel
        # cells and the browser would clip most of the text off the strip.
        cell = max(WINDOW, -(-len(text) // MAX_CELLS))
        strip = []
        for s in range(0, len(text), cell):
            seg = ev[s : s + cell]
            strip.append({"start": s, "end": s + len(seg), "mean": sum(seg) / max(len(seg), 1)})
        means = sorted(abs(c["mean"]) for c in strip if c["mean"])
        strip_scale = means[int(0.95 * (len(means) - 1))] if means else 1.0

        contrib = sorted(((counts[g] * weight[g], g) for g in counts), reverse=True)

        def row(w: float, g: str) -> dict[str, Any]:
            return {
                "gram": g,
                "hits": counts[g],
                "count_a": profiles[a].get(g, 0),
                "count_b": profiles[b].get(g, 0),
                "rate_a": round(per100k(a, g), 1),
                "rate_b": round(per100k(b, g), 1),
                "weight": round(w, 2),
            }

        def seen_in_either(g: str) -> bool:
            # A string absent from both profiles carries only the smoothing
            # asymmetry (it favours the smaller profile); it is not evidence.
            return profiles[a].get(g, 0) > 0 or profiles[b].get(g, 0) > 0

        result.update(
            {
                "verdict": "low evidence" if len(counts) < LOW_EVIDENCE else "leans",
                "first": first,
                "second": second,
                "margin": round(margin, 3),
                "gap": round(score[first] - score[second], 1),
                "pair": {"a": a, "b": b, "pinned": pair is not None,
                         "gap": round(score[a] - score[b], 1)},
                "ranking": [{"label": lab, "delta": round(score[lab] - score[first], 1)} for lab in ranked],
                "strip": strip,
                "strip_cell": cell,
                "strip_scale": strip_scale,
                "excerpt": {
                    "start": offset,
                    "end": min(offset + EXCERPT, len(text)),
                    "text": text[offset : offset + EXCERPT],
                    "evidence": [round(e, 4) for e in ev[offset : offset + EXCERPT]],
                },
                "scale": scale,
                "for": [row(w, g) for w, g in contrib if w > 0 and seen_in_either(g)][:12],
                "against": [row(w, g) for w, g in reversed(contrib) if w < 0 and seen_in_either(g)][:12],
            }
        )
        return result
