"""Which corpus the environment names, and what the agent client sends.

`open_corpus_from_env` is the one place every front end builds its Source.
A plain-text folder with a manifest (LocalReader) is now the first thing it
looks for, because that is how Radich's files become the corpus the agents,
the Corpus tab and the Evidence tab all read together.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cohort import attribution as attr
from cohort.agents.openrouter import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    OpenRouterError,
    complete,
    output_limits_from_env,
)
from cohort.sources.env import open_corpus_from_env
from cohort.sources.local_reader import LocalReader
from cohort.sources.radich_manifest import write_manifest

FIXTURE = Path(__file__).parent.parent / "examples" / "local_corpus"


def test_a_local_corpus_root_wins_over_the_archive(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_CORPUS_ROOT", str(FIXTURE))
    monkeypatch.setenv("CBETA_ARCHIVE_PATH", "/nowhere.zip")
    source, reason = open_corpus_from_env(repo_root=tmp_path)
    try:
        assert reason is None
        assert isinstance(source, LocalReader)
        assert source.search("明月")
    finally:
        source.close()


def test_a_bad_local_root_explains_itself(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_CORPUS_ROOT", str(tmp_path / "missing"))
    monkeypatch.delenv("CBETA_ARCHIVE_PATH", raising=False)
    source, reason = open_corpus_from_env(repo_root=tmp_path)
    assert source is None
    assert "LOCAL_CORPUS_ROOT" in reason


def test_no_corpus_names_both_variables(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCAL_CORPUS_ROOT", raising=False)
    monkeypatch.delenv("CBETA_ARCHIVE_PATH", raising=False)
    source, reason = open_corpus_from_env(repo_root=tmp_path)
    assert source is None
    assert "LOCAL_CORPUS_ROOT" in reason
    assert "CBETA_ARCHIVE_PATH" in reason


def test_radich_manifest_lists_catalogued_base_texts(tmp_path):
    corpus = tmp_path / attr.CORPUS_DIR
    for uid, text in (("T0001", "一二三"), ("T0002", "四五六"), ("T9999", "七八九")):
        (corpus / uid).mkdir(parents=True)
        (corpus / uid / "大.txt").write_text(text, encoding="utf-8")
    (corpus / "T0003").mkdir()  # in the catalogue, no base text
    (tmp_path / attr.CATALOGUE).write_bytes(b"T0001 A\r\nT0002 grey\r\nT0003 A\r\n")
    ledger = write_manifest(tmp_path)
    assert ledger == {"listed": 2, "skipped: not in catalogue": 1, "skipped: no base text": 1}
    rows = list(csv.DictReader((corpus / "manifest.csv").open(encoding="utf-8")))
    assert [r["path"] for r in rows] == ["T0001/大.txt", "T0002/大.txt"]
    assert rows[0]["witness_ref"] == "T0001"
    assert rows[1]["label"] == "T0002 · grey"
    reader = LocalReader(corpus)
    try:
        assert reader.fetch("T0001/大.txt").witness_ref == "T0001"
        assert reader.search("四五")[0].ref == "T0002/大.txt"
    finally:
        reader.close()
    ledger = write_manifest(tmp_path, include_uncatalogued=True)
    assert ledger["listed"] == 3


@pytest.fixture
def no_dotenv(monkeypatch):
    """These tests are about the process environment; a developer's real .env
    in the repository root must not leak into them."""
    monkeypatch.setattr("cohort.agents.openrouter._load_dotenv", lambda *a, **k: None)


def test_output_limits_default_to_the_module_ceiling(monkeypatch, no_dotenv):
    monkeypatch.delenv("OPENROUTER_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)
    assert output_limits_from_env() == (DEFAULT_MAX_OUTPUT_TOKENS, None)


@pytest.mark.parametrize("raw", ["0", "none", "OFF"])
def test_the_ceiling_can_be_lifted_from_the_environment(monkeypatch, no_dotenv, raw):
    monkeypatch.setenv("OPENROUTER_MAX_OUTPUT_TOKENS", raw)
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "low")
    assert output_limits_from_env() == (None, "low")


def test_bad_limits_are_config_errors(monkeypatch, no_dotenv):
    monkeypatch.setenv("OPENROUTER_MAX_OUTPUT_TOKENS", "lots")
    with pytest.raises(OpenRouterError, match="integer"):
        output_limits_from_env()
    monkeypatch.setenv("OPENROUTER_MAX_OUTPUT_TOKENS", "4000")
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "maximal")
    with pytest.raises(OpenRouterError, match="one of"):
        output_limits_from_env()


def test_reasoning_effort_is_forwarded_to_the_provider():
    seen: dict = {}

    def transport(url, headers, body, timeout):
        seen.update(json.loads(body))
        return 200, json.dumps({
            "id": "x", "model": "m",
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }).encode()

    complete("m", [], [], api_key="k", transport=transport, max_output_tokens=None, reasoning_effort="low")
    assert "max_tokens" not in seen
    assert seen["reasoning"] == {"effort": "low"}
