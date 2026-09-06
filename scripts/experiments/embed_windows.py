"""Embed every unit of Radich's corpus, labelled and grey, with a frozen encoder.

    uv run --with torch --with transformers --with numpy \
        python -m scripts.experiments.embed_windows buddhist-nlp/mitra-qwen35-embedder data/radich \
        --out ~/corpora/embeddings/mitra-qwen35-embedder.npz

Nothing is trained. Each text is cut into fixed windows so that (a) we stay
under the encoder's 512-token limit, (b) a unit's vector is the mean of its
windows, so length does not dominate, and (c) `cohort.embeddings` can later
look for the passages elsewhere that read like each window. The model card's
recipe is followed exactly: passages are raw text, last-token pooling with
left padding, L2-normalised.

Writes an .npz with `vec` (float16, L2-normalised), `uid`, `label`, `start`
(character offset of each window), which is what `cohort.embeddings` reads.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from cohort.attribution import CATALOGUE, AttributionIndex, read_catalogue

WINDOW = 400          # characters; roughly one token per CJK character, so under 512 tokens
MAX_TOKENS = 512      # the model card's limit


def windows(root: str) -> list[tuple[str, str, int, str]]:
    from pathlib import Path

    labels, _, _ = read_catalogue(Path(root) / CATALOGUE)
    out = []
    for uid, label in labels.items():
        text = AttributionIndex.base_text(Path(root), uid)
        if text is None:
            continue
        for start in range(0, len(text), WINDOW):
            piece = text[start : start + WINDOW]
            if len(piece) >= WINDOW // 2:   # a 30-character tail is not a sample of anything
                out.append((uid, label, start, piece))
    if not out:
        msg = "no windows produced; check the corpus path"
        raise SystemExit(msg)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model")
    ap.add_argument("root")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    # Optional, GPU-only dependencies: run with `uv run --with torch --with transformers`.
    import torch  # ty: ignore[unresolved-import]
    from transformers import AutoModel, AutoTokenizer  # ty: ignore[unresolved-import]

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(args.model)
    tok.padding_side = "left"                        # last-token pooling needs this
    model = AutoModel.from_pretrained(args.model, dtype=torch.bfloat16, device_map="cuda").eval()
    print(f"model {args.model}  dim {model.config.hidden_size}  loaded in {time.time() - t0:.0f}s", file=sys.stderr)

    W = windows(args.root)
    print(f"windows {len(W):,} from {len({w[0] for w in W}):,} units", file=sys.stderr)
    vecs = np.zeros((len(W), model.config.hidden_size), dtype=np.float16)
    texts = [w[3] for w in W]
    truncated = 0
    with torch.inference_mode():
        for i in range(0, len(texts), args.batch):
            enc = tok(texts[i : i + args.batch], padding=True, truncation=True,
                      max_length=MAX_TOKENS, return_tensors="pt")
            truncated += int((enc["attention_mask"].sum(1) == MAX_TOKENS).sum())
            enc = enc.to(model.device)
            h = model(**enc).last_hidden_state[:, -1]
            v = torch.nn.functional.normalize(h.float(), dim=-1)
            if not torch.isfinite(v).all():
                msg = f"non-finite embedding at batch {i}"
                raise SystemExit(msg)
            vecs[i : i + args.batch] = v.cpu().numpy().astype(np.float16)
            if (i // args.batch) % 200 == 0:
                done = i + args.batch
                rate = done / max(time.time() - t0, 1e-9)
                print(f"  {done:>7,}/{len(texts):,}  eta {(len(texts) - done) / max(rate, 1e-9) / 60:5.1f} min", file=sys.stderr)

    # Sanity before saving: two windows of one text must be closer than two of
    # different texts, or the pooling is wrong.
    uid = np.array([w[0] for w in W])
    rng = np.random.default_rng(0)
    same, diff = [], []
    for _ in range(3000):
        a, b = rng.integers(len(W), size=2)
        s = float(vecs[a].astype(np.float32) @ vecs[b].astype(np.float32))
        (same if uid[a] == uid[b] else diff).append(s)
    print(f"cosine same-unit {np.mean(same) if same else float('nan'):.3f}  "
          f"different-unit {np.mean(diff):.3f}  truncated windows {truncated}", file=sys.stderr)
    np.savez(args.out, vec=vecs, uid=uid, start=np.array([w[2] for w in W], dtype=np.int32),
             label=np.array([w[1] for w in W]))
    print(f"wrote {args.out}  total {(time.time() - t0) / 60:.1f} min", file=sys.stderr)


if __name__ == "__main__":
    main()
