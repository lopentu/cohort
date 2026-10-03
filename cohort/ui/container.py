"""Container configuration adapts to the existing localhost UI launcher."""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from cohort.graph import Graph


def server_arguments(env: Mapping[str, str]) -> list[str]:
    args = ['--db', env.get('COHORT_DB', '/state/research.sqlite'),
            '--log', env.get('COHORT_LOG', '/state/research.jsonl'),
            '--auth-file', env.get('COHORT_AUTH_FILE', '/state/ui-auth.json'), '--host', '127.0.0.1',
            '--port', env.get('COHORT_PORT', '18766')]
    for key, flag in [('COHORT_ROOT_PATH', '--root-path'), ('COHORT_PUBLIC_ORIGIN', '--public-origin'),
                      ('COHORT_TRUSTED_PROXY_IPS', '--trusted-proxy-ips')]:
        if env.get(key):
            args.extend([flag, env[key]])
    for key, flag in [('COHORT_ALLOW_WRITES', '--allow-writes'),
                      ('COHORT_ALLOW_RUNS', '--allow-runs'),
                      ('COHORT_NO_BUDGET', '--no-budget')]:
        value = env.get(key, '0')
        if value not in ('0', '1'):
            raise ValueError(f'{key} must be 0 or 1')
        if value == '1':
            args.append(flag)
    if env.get('LOCAL_CORPUS_ROOT') or env.get('CBETA_ARCHIVE_PATH'):
        args.append('--corpus')
    if env.get('COHORT_RADICH_ROOT'):
        args.extend(['--radich', env['COHORT_RADICH_ROOT']])
    return args


def ensure_graph(db: Path, log: Path) -> None:
    """Create a new empty workspace or replay an existing log; never reseed one."""
    if db.exists():
        return
    db.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with Graph.open(db, log):
        pass


def main() -> None:
    from cohort.agents.openrouter import _load_dotenv
    from cohort.ui.auth import AuthManager
    from cohort.ui.hosting import HostingConfig

    _load_dotenv()
    # Check credentials before creating any research state. Reuse the launcher's
    # verifier rather than introducing a weaker container-only login path.
    try:
        hosting = HostingConfig(os.environ.get('COHORT_ROOT_PATH', ''),
                                os.environ.get('COHORT_PUBLIC_ORIGIN') or None,
                                os.environ.get('COHORT_TRUSTED_PROXY_IPS') or None)
        AuthManager.from_file(os.environ.get('COHORT_AUTH_FILE', '/state/ui-auth.json'),
                              allow_local_http=hosting.public_origin is None,
                              root_path=hosting.root_path, public_origin=hosting.public_origin)
        args = server_arguments(os.environ)
        ensure_graph(Path(args[1]), Path(args[3]))
    except (OSError, ValueError) as exc:
        raise SystemExit('Container startup failed. Check account setup, state permissions '
                         'and configuration.') from exc
    script = Path(__file__).resolve().parents[2] / 'scripts/serve_ui.py'
    os.execv(sys.executable, [sys.executable, str(script), *args])
