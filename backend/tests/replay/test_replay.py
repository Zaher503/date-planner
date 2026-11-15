"""Replay every saved import case offline and compare the prepared hints with the expected ones."""
from pathlib import Path

import pytest

from app.replay import load_case, replay

CASES = sorted(p for p in (Path(__file__).parent / "cases").iterdir() if p.is_dir())


@pytest.mark.parametrize("folder", CASES, ids=lambda p: p.name)
def test_saved_case(folder):
    case = load_case(folder)
    assert case.expected is not None, "expected.json is missing"
    got, tape = replay(case)
    assert tape.misses == [], "the pipeline asked for something the case did not record"
    assert not tape.unused, f"saved model answers never asked for: {[case.model[i]['system'] for i in tape.unused]}"
    assert got == case.expected


def test_there_are_cases():
    assert len(CASES) >= 3
