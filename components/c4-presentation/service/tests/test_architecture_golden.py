"""Behaviour-preserving refactors must reproduce the golden baseline captured before the V3.1 consolidation."""
import json

import pytest

from tests import architecture_golden as golden

EXPECTED = json.loads(golden.FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("part", sorted(golden.PARTS))
def test_part_matches_the_pre_refactor_baseline(part):
    if part in ("http",) and not golden.CHECKPOINT.is_file():
        pytest.skip("local trained checkpoint not present")
    actual = json.loads(json.dumps(golden.PARTS[part]()))
    if part == "kernels" and not golden.CHECKPOINT.is_file():
        expected = {k: v for k, v in EXPECTED[part].items() if not k.startswith("checkpoint")}
        actual = {k: v for k, v in actual.items() if not k.startswith("checkpoint")}
    else:
        expected = EXPECTED[part]
    assert golden.differences(expected, actual) == []
