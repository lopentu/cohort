"""Creation provenance must survive later changes to an agent's model."""
from cohort.graph import Graph
from cohort.schemas import QueryPayload
from cohort.views import node_detail_json


def test_creation_uses_causal_model_call(tmp_path):
    db, log = tmp_path / 'graph.sqlite', tmp_path / 'graph.jsonl'
    with Graph.open(db, log) as graph:
        call = graph.log_model_call(authored_by='agent:worker', model='family/original')
        node_id = graph.propose_query(
            QueryPayload(text='needle'), authored_by='agent:worker', model_call_id=call.seq,
        )
        graph.log_model_call(authored_by='agent:worker', model='family/later')
        result = node_detail_json(graph, node_id, log_path=log)
        assert result['created_by']['author'] == 'agent:worker'
        assert result['created_by']['model'] == 'family/original'


def test_missing_log_does_not_guess_model(tmp_path):
    with Graph.open(tmp_path / 'graph.sqlite', tmp_path / 'graph.jsonl') as graph:
        node_id = graph.propose_query(QueryPayload(text='needle'), authored_by='agent:worker')
        result = node_detail_json(graph, node_id, log_path=tmp_path / 'absent.jsonl')
        assert result['created_by'] is None
