"""Related retrieval must preserve positions and exclude the entire target work."""
import pytest

from cohort.embeddings import EmbeddingIndex
from cohort.related import related_passages

np = pytest.importorskip("numpy")


@pytest.fixture
def inputs(tmp_path):
    path = tmp_path / "test.npz"
    np.savez(path, vec=np.array([[1., 0.], [1., 0.], [.8, .6], [0., 1.]]),
             uid=['T0001-1', 'T0001-2', 'T0002', 'T0003'],
             start=[0, 0, 0, 0], label=['A', 'A', 'B', 'C'])

    class Corpus:
        root = tmp_path

        def base_text(self, root, uid):
            return {'T0001-1': '甲，乙丙丁戊己', 'T0002': '甲乙，丙丁戊己',
                    'T0003': '天地玄黃'}[uid]

    return EmbeddingIndex(path), Corpus()


def test_related_excludes_sibling_and_locates_shared_wording(inputs):
    embeddings, corpus = inputs
    result = related_passages(embeddings, corpus, 'T0001-1', start=0, limit=3)
    assert [r['uid'] for r in result['matches']] == ['T0002', 'T0003']
    assert result['matches'][0]['cosine'] == .8
    run = result['matches'][0]['shared_runs'][0]
    assert run['chars'] == 6
    assert run['a_start'] == 0 and run['a_end'] == 7
    assert run['b_start'] == 0 and run['b_end'] == 7
    assert result['query']['text'][run['a_start']:run['a_end']] == '甲，乙丙丁戊己'
    assert result['matches'][1]['shared_runs'] == []


def test_unknown_position_is_not_silently_replaced(inputs):
    with pytest.raises(ValueError, match='indexed position'):
        related_passages(*inputs, 'T0001-1', start=123)


def test_unknown_text_is_not_a_free_text_query(inputs):
    with pytest.raises(KeyError):
        related_passages(*inputs, 'a research question')


def test_http_related_read_only_and_validation(inputs, tmp_path):
    from fastapi.testclient import TestClient

    from cohort.ui.api import create_app

    embeddings, corpus = inputs
    client = TestClient(create_app(tmp_path / 'unused.sqlite', attribution=corpus,
                                   embeddings=embeddings))
    assert client.get('/api/corpus/related').json()['enabled'] is True
    response = client.get('/api/corpus/related', params={'uid': 'T0001-1'})
    assert response.status_code == 200
    assert response.json()['matches'][0]['uid'] == 'T0002'
    assert client.get('/api/corpus/related?uid=T0001-1&start=123').status_code == 422
    assert client.get('/api/corpus/related?uid=T9999').status_code == 404
    assert not (tmp_path / 'unused.sqlite').exists()


def test_http_unconfigured_is_explicit(tmp_path):
    from fastapi.testclient import TestClient

    from cohort.ui.api import create_app

    client = TestClient(create_app(tmp_path / 'unused.sqlite'))
    assert client.get('/api/corpus/related').json()['enabled'] is False
    assert client.get('/api/corpus/related?uid=T0001').status_code == 503
