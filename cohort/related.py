"""Inspect one indexed passage and its neighbours without writing graph records."""
from __future__ import annotations

import difflib
import hashlib
from typing import Any

from cohort.attribution import AttributionIndex, work_of
from cohort.embeddings import EmbeddingIndex
from cohort.tools.align_passages import _han_only


def related_config(embeddings: EmbeddingIndex | None) -> dict[str, Any]:
    if embeddings is None:
        return {"enabled": False, "reason": "No passage embeddings are configured."}
    return {
        "enabled": True,
        "index_file": embeddings.path.name,
        # Legacy indexes contain vectors and positions, but no model manifest.
        # A filename must not masquerade as verified training provenance.
        "model_from_filename": embeddings.path.stem,
        "model_revision": None,
        "provenance_note": "Model name comes from the index filename; revision and training inputs are not recorded.",
        "windows": len(embeddings.uid),
        "units": sorted(set(embeddings.uid.tolist())),
        "dimensions": int(embeddings.vec.shape[1]),
        "window_chars": embeddings.window,
        "method": "Cosine similarity of stored passage vectors",
    }


def _passage(index: AttributionIndex, uid: str, start: int, window: int) -> dict[str, Any]:
    text = index.base_text(index.root, uid)
    if text is None:
        raise KeyError(f"No source text for {uid}")
    if start < 0 or start >= len(text):
        raise ValueError(f"Indexed position {start} is outside the current source for {uid}")
    return {"uid": uid, "start": start, "end": min(start + window, len(text)),
            "text": text[start:start + window],
            "source_sha256": hashlib.sha256(text.encode()).hexdigest()}


def related_passages(
    embeddings: EmbeddingIndex, index: AttributionIndex, uid: str,
    *, start: int = 0, limit: int = 5,
) -> dict[str, Any]:
    """Rank windows in other works, with bounded exact-overlap checks on each pair."""
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    np = embeddings._np
    mine = np.where(embeddings.uid == uid)[0]
    if not len(mine):
        raise KeyError(f"{uid} has no indexed passages")
    selected = mine[embeddings.start[mine] == start]
    if not len(selected):
        raise ValueError(f"{start} is not an indexed position for {uid}")
    query = _passage(index, uid, start, embeddings.window)
    pool = np.where(embeddings.work != work_of(uid))[0]
    sims = embeddings.vec[pool].astype(np.float32) @ embeddings.vec[selected[0]].astype(np.float32)
    order = np.argsort(-sims, kind="stable")[:limit]
    ha, oa = _han_only(query['text'])
    matches = []
    for j in order:
        i = pool[j]
        passage = _passage(index, str(embeddings.uid[i]), int(embeddings.start[i]), embeddings.window)
        hb, ob = _han_only(passage['text'])
        blocks = difflib.SequenceMatcher(None, ha, hb, autojunk=False).get_matching_blocks()
        runs = [
            {"chars": b.size, "text": ha[b.a:b.a + b.size],
             "a_start": start + oa[b.a], "a_end": start + oa[b.a + b.size - 1] + 1,
             "b_start": passage['start'] + ob[b.b],
             "b_end": passage['start'] + ob[b.b + b.size - 1] + 1}
            for b in sorted(blocks, key=lambda b: -b.size) if b.size >= 4
        ]
        passage.update(cosine=round(float(sims[j]), 3), shared_runs=runs,
                       longest_shared_run=max((b.size for b in blocks), default=0))
        matches.append(passage)
    return {
        "query": query, "matches": matches,
        "positions": embeddings.start[mine].tolist(),
        "same_work_excluded": True, "candidate_windows": len(pool),
        "index": related_config(embeddings),
        "limitations": "Similarity suggests passages to read, not a translator or direction of borrowing. Shared wording is checked only within the displayed windows. Index-to-source hashes were not recorded when these embeddings were created.",
    }
