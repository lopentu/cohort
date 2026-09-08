"""The analyst can inspect evidence but cannot change research records."""
from pathlib import Path

import pytest

from cohort.agents.analysis_worker import AnalysisWorker
from cohort.schemas import ClaimPayload
from cohort.sources.local_reader import LocalReader


@pytest.fixture
def source():
    reader = LocalReader(Path(__file__).parent.parent / 'examples' / 'local_corpus')
    yield reader
    reader.close()



def test_analyst_cannot_propose_or_review(graph, source):
    worker = AnalysisWorker(graph, source, authored_by='agent:reader', model='test/model', api_key='test')
    names = {t['function']['name'] for t in worker.tools}
    assert 'inspect_node' in names
    assert names.isdisjoint({'propose_claim', 'propose_conjecture', 'review_claim', 'find_attestations'})
    before = graph._snapshot()
    error, _ = worker._dispatch('propose_claim', {'text': 'not allowed'})
    assert error
    assert graph._snapshot() == before


def test_analyst_reads_record_with_provenance(graph, source):
    node = graph.propose_claim(ClaimPayload(text='Synthetic claim'), authored_by='agent:author')
    worker = AnalysisWorker(graph, source, authored_by='agent:reader', model='test/model', api_key='test')
    error, result = worker._dispatch('inspect_node', {'node_id': node})
    assert not error
    assert result['payload']['text'] == 'Synthetic claim'
    assert result['authorship'][0]['author'] == 'agent:author'
