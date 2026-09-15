"""result.json: the machine-readable hand-off from a notebook to the site's /write-post.

The site draft takes `result` (the scored sentence), `findings`, `subject`,
`datasets`, and the figure list from here rather than from prose, so no
number is retyped. `field_check.status` is `pending` until the author has
filled field/observations.csv; a post is never drafted from a pending result.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

SCHEMA = "purespatial-result/1"
REQUIRED = ("slug", "subject", "datasets", "method", "predictions", "field_check", "score", "result", "findings", "figures")


def _clean(o):
    """Plain JSON types only: numpy scalars and arrays unwrapped, NaN to null, paths and dates to strings."""
    import math

    import numpy as np

    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_clean(v) for v in o.tolist()]
    if isinstance(o, np.generic):
        return _clean(o.item())
    if isinstance(o, bool) or o is None or isinstance(o, (int, str)):
        return o
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if hasattr(o, "to_dict"):
        return _clean(o.to_dict())
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def write_result(path: str | Path, **payload) -> Path:
    missing = [k for k in REQUIRED if k not in payload]
    if missing:
        raise ValueError(f"result.json is missing {missing}")
    doc = {
        "schema": SCHEMA,
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **payload,
    }
    path = Path(path)
    path.write_text(json.dumps(_clean(doc), indent=2, allow_nan=False) + "\n")
    return path


def read_result(path: str | Path) -> dict:
    doc = json.loads(Path(path).read_text())
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {doc.get('schema')!r}, expected {SCHEMA!r}")
    return doc
