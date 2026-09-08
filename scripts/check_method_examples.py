"""Reproduce aggregate example results without exporting restricted source passages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cohort.attribution import AttributionIndex
from cohort.embeddings import EmbeddingIndex
from cohort.related import related_passages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--radich', required=True)
    parser.add_argument('--embeddings', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--uid', action='append')
    args = parser.parse_args()
    index = AttributionIndex.load(args.radich)
    embeddings = EmbeddingIndex(args.embeddings)
    units = args.uid or ['T0263-rest', 'T0262-exDevadatta', 'T0603']
    report = {'selection': 'Illustrative known relationships, selected after inspecting candidate outputs; not an accuracy benchmark.',
              'index_file': embeddings.path.name,
              'index_sha256': hashlib.file_digest(embeddings.path.open('rb'), 'sha256').hexdigest(),
              'coverage': {k: v for k, v in embeddings.describe().items() if k != 'file'},
              'cases': []}
    for uid in units:
        neighbors = embeddings.neighbors(uid, max_windows=1)
        vocabulary = []
        for features in ['radich', 'generic']:
            evidence = index.evidence(uid, features)
            vocabulary.append({k: evidence[k] for k in
                               ['features', 'label', 'first', 'second', 'margin', 'distinct', 'hits', 'withheld_units']})
        # A reproducible non-opening window, not the best result selected by score.
        pair = related_passages(embeddings, index, uid, start=4000, limit=1)
        match = pair['matches'][0]
        report['cases'].append({
            'uid': uid, 'vocabulary': vocabulary,
            'windows': neighbors['windows'],
            'nearest_unit_tally': neighbors['nearest_unit_tally'],
            'nearest_label_tally': neighbors['nearest_label_tally'],
            'example_window': {'start': 4000, 'nearest_uid': match['uid'],
                               'nearest_start': match['start'], 'cosine': match['cosine'],
                               'longest_shared_run': match['longest_shared_run']},
        })
        print(f"Measured {uid}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
