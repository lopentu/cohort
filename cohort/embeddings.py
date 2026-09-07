"""Precomputed window embeddings, read for nearest-passage retrieval.

A frozen encoder (Dharmamitra's Buddhist-Chinese models, run once elsewhere)
turned every 400-character window of Radich's corpus into a vector; this
module reads the `.npz` it wrote and answers one question: which windows in
*other* works read most like this one. That is the question such an encoder
is good at. It is not good at translator identity -- 23.7% same-translator
retrieval against a 24.0% largest-class baseline -- so nothing here ranks
translators; it finds passages a reader should compare, such as a commentary
quoting the text under study.

numpy is the only dependency, and it is imported lazily so the rest of the
package stays standard-library when no embeddings are configured.
"""

from __future__ import annotations

import collections
import os
from pathlib import Path
from typing import Any

from cohort.attribution import work_of

ENV_PATH = "EVIDENCE_EMBEDDINGS_PATH"


class EmbeddingIndex:
    """One `.npz` of L2-normalised window vectors with their unit, label and offset."""

    def __init__(self, path: str | Path) -> None:
        try:
            import numpy as np
        except ModuleNotFoundError as e:  # pragma: no cover - environment-dependent
            msg = "the semantic-neighbours tool needs numpy: uv sync --extra evidence"
            raise RuntimeError(msg) from e
        self.path = Path(path)
        if not self.path.is_file():
            msg = f"no embeddings file at {self.path}"
            raise FileNotFoundError(msg)
        z = np.load(self.path)
        for key in ("vec", "uid", "label", "start"):
            if key not in z:
                msg = f"{self.path.name} lacks the '{key}' array"
                raise ValueError(msg)
        self._np = np
        self.vec = z["vec"]  # float16 on disk; cast per query, not whole
        self.uid = z["uid"].astype(str)
        self.label = z["label"].astype(str)
        self.start = z["start"].astype(int)
        self.work = np.array([work_of(u) for u in self.uid])
        self.window = int(self._infer_window())
        if len({len(self.vec), len(self.uid), len(self.label), len(self.start)}) != 1:
            msg = f"{self.path.name}: arrays disagree in length"
            raise ValueError(msg)

    def _infer_window(self) -> int:
        """The window length is the smallest positive gap between consecutive offsets of one unit."""
        np = self._np
        gaps = np.diff(self.start)
        same = self.uid[1:] == self.uid[:-1]
        positive = gaps[same & (gaps > 0)]
        return int(positive.min()) if len(positive) else 400

    @classmethod
    def from_env(cls) -> EmbeddingIndex | None:
        """The configured index, or None when none is configured (a feature switched off)."""
        path = os.environ.get(ENV_PATH)
        return cls(path) if path else None

    def describe(self) -> dict[str, Any]:
        return {
            "file": str(self.path),
            "windows": len(self.uid),
            "units": len(set(self.uid)),
            "dim": int(self.vec.shape[1]),
            "window_chars": self.window,
        }

    def neighbors(
        self, uid: str, *, top_k: int = 3, max_windows: int = 6, labelled_only: bool = False,
    ) -> dict[str, Any]:
        """For the first `max_windows` windows of `uid`, the `top_k` most similar
        windows in *other works*; plus a tally, over all of `uid`'s windows, of
        which unit and which label the single nearest window belongs to.

        Same-work windows are excluded, always: a chapter's nearest neighbour is
        its own next chapter, which tells a reader nothing.
        """
        np = self._np
        mine = np.where(self.uid == uid)[0]
        if not len(mine):
            msg = f"{uid} has no windows in {self.path.name}"
            raise KeyError(msg)
        other = self.work != self.work[mine[0]]
        if labelled_only:
            other &= self.label != "grey"
        pool = np.where(other)[0]
        pool_vec = self.vec[pool].astype(np.float32)
        out: list[dict[str, Any]] = []
        nearest_unit: collections.Counter[str] = collections.Counter()
        nearest_label: collections.Counter[str] = collections.Counter()
        for n, i in enumerate(mine):
            sims = pool_vec @ self.vec[i].astype(np.float32)
            order = np.argsort(-sims)
            best = pool[order[0]]
            nearest_unit[str(self.uid[best])] += 1
            nearest_label[str(self.label[best])] += 1
            if n < max_windows:
                out.append({
                    "start": int(self.start[i]),
                    "neighbors": [
                        {
                            "uid": str(self.uid[pool[j]]),
                            "label": str(self.label[pool[j]]),
                            "start": int(self.start[pool[j]]),
                            "cosine": round(float(sims[j]), 3),
                        }
                        for j in order[:top_k]
                    ],
                })
        return {
            "uid": uid,
            "windows": len(mine),
            "window_chars": self.window,
            "shown": out,
            "nearest_unit_tally": nearest_unit.most_common(8),
            "nearest_label_tally": nearest_label.most_common(8),
            "same_work_excluded": True,
            "labelled_only": labelled_only,
        }
