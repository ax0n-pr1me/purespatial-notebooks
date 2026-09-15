import numpy as np
import pytest

from purespatial import result


def _payload(**over):
    base = {
        "slug": "x", "subject": {"name": "X"}, "datasets": ["3dep-lidar"], "method": {}, "predictions": [],
        "field_check": {"status": "pending"}, "score": None, "result": None, "findings": [], "figures": [],
    }
    base.update(over)
    return base


def test_roundtrip_with_numpy_values(tmp_path):
    p = result.write_result(tmp_path / "result.json", **_payload(score={"n": np.int64(3), "f": np.float64(0.5), "nan": np.float64("nan"), "b": np.bool_(True)}))
    doc = result.read_result(p)
    assert doc["schema"] == result.SCHEMA and doc["generated"].endswith("+00:00")
    assert doc["score"] == {"n": 3, "f": 0.5, "nan": None, "b": True}


def test_missing_required_key_is_refused(tmp_path):
    payload = _payload()
    del payload["figures"]
    with pytest.raises(ValueError):
        result.write_result(tmp_path / "r.json", **payload)


def test_wrong_schema_is_refused(tmp_path):
    (tmp_path / "r.json").write_text('{"schema": "other"}')
    with pytest.raises(ValueError):
        result.read_result(tmp_path / "r.json")
