import asyncio
from pathlib import Path

from scripts import run_eval_ci


def test_run_eval_ci_skips_when_golden_fixture_missing(monkeypatch):
    missing_fixture = Path(__file__).resolve().parent / "fixtures" / "does-not-exist.json"
    monkeypatch.setattr(run_eval_ci, "GOLDEN_PATH", missing_fixture)

    result = asyncio.run(run_eval_ci.main())

    assert result == 0
