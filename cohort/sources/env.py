"""Building the CBETA reader from the environment, in one place.

Every front end needs the same corpus: the CLI, the web API and the manual
scripts. When each built its own, "the same query returns the same hits
whichever way you ask" was a claim resting on eight copies of a hash constant
and three slightly different constructor calls. Now it rests on this function.

The hash is here rather than in a script because the provenance argument
depends on it: a witness node claims to come from a specific archive, and eight
copies of that expectation are eight chances for one to drift.
"""
from __future__ import annotations

import os
from pathlib import Path

from .base import Source

#: SHA-256 of `CBETA_電子佛典_xml_v061_20210710.zip`, verified independently
#: against the real file. See docs/corpus.md — if this does not match, stop.
CBETA_V061_SHA256 = "90a663f212bc854e6a758ed06c74776cef5cbf8e7040d0192ff3301e6f7158f2"

DEFAULT_FTS_FILENAME = "cbeta_fts.sqlite"


def open_corpus_from_env(
    *, repo_root: Path | None = None, require_search: bool = True,
) -> tuple[Source | None, str | None]:
    """`(source, unavailable_reason)` — never both, never neither.

    Returns `None` with an explanation rather than raising, because every
    caller is useful without a corpus: the graph is already there, and a
    missing archive should disable a feature rather than refuse to start.
    The explanation is returned rather than printed so the caller decides
    where it goes — stderr for a CLI, a JSON field for an API.

    `require_search=True` also refuses when no FTS index exists, since
    `search()` would raise on first use; a caller that only needs `fetch()`
    can pass False and get a reader without one.
    """
    from cohort.agents.openrouter import _load_dotenv

    from .cbeta_fts import CbetaFtsIndex
    from .cbeta_reader import CbetaArchiveError, CbetaReader

    root = repo_root or Path.cwd()
    _load_dotenv(root / ".env")

    archive = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive:
        return None, "CBETA_ARCHIVE_PATH is not set"

    fts_path = Path(os.environ.get("CBETA_FTS_PATH") or (root / DEFAULT_FTS_FILENAME))
    try:
        fts = CbetaFtsIndex(fts_path, CBETA_V061_SHA256) if fts_path.is_file() else None
        if fts is None and require_search:
            return None, (
                f"no FTS index at {fts_path}, so search would raise. "
                "Build it: .venv/bin/python scripts/build_cbeta_index.py"
            )
        return CbetaReader(archive, CBETA_V061_SHA256, fts=fts), None
    except CbetaArchiveError as e:
        return None, str(e)
