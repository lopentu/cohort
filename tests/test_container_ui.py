"""Container startup preserves saved research and keeps server capabilities explicit."""
from pathlib import Path

from cohort.graph import Graph
from cohort.ui.container import ensure_graph, server_arguments


def test_default_container_is_local_and_read_only():
    args = server_arguments({})
    assert args[args.index('--host') + 1] == '127.0.0.1'
    assert '--allow-runs' not in args
    assert '--allow-writes' not in args
    assert '--no-auth' not in args
    assert '--no-budget' not in args


def test_features_and_persistent_paths_are_forwarded():
    args = server_arguments({'COHORT_ALLOW_RUNS': '1', 'COHORT_ALLOW_WRITES': '1',
                             'COHORT_RADICH_ROOT': '/inputs/radich',
                             'LOCAL_CORPUS_ROOT': '/inputs/corpus', 'COHORT_PORT': '18768'})
    assert '--allow-runs' in args
    assert '--allow-writes' in args
    assert '--corpus' in args
    assert args[args.index('--radich') + 1] == '/inputs/radich'
    assert args[args.index('--port') + 1] == '18768'
    assert '--no-budget' not in args
    assert '--no-budget' in server_arguments({'COHORT_ALLOW_RUNS': '1', 'COHORT_NO_BUDGET': '1'})


def test_restart_keeps_saved_graph_bytes(tmp_path: Path):
    db, log = tmp_path / 'research.sqlite', tmp_path / 'research.jsonl'
    ensure_graph(db, log)
    with Graph.open_read_only(db) as graph:
        assert graph.nodes() == []
    before = db.read_bytes()
    ensure_graph(db, log)
    assert db.read_bytes() == before


def test_hosted_configuration_is_forwarded_and_secrets_are_external():
    args = server_arguments({'COHORT_ROOT_PATH': '/cohort',
                             'COHORT_PUBLIC_ORIGIN': 'https://lopen.linguistics.ntu.edu.tw',
                             'COHORT_TRUSTED_PROXY_IPS': '127.0.0.1',
                             'COHORT_AUTH_FILE': '/secrets/ui-auth.json'})
    assert args[args.index('--root-path') + 1] == '/cohort'
    assert args[args.index('--public-origin') + 1] == 'https://lopen.linguistics.ntu.edu.tw'
    assert args[args.index('--trusted-proxy-ips') + 1] == '127.0.0.1'
    assert args[args.index('--auth-file') + 1] == '/secrets/ui-auth.json'
