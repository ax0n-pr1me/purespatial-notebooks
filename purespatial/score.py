"""Predictions against field observations, and the one result sentence.

A prediction is `visible` or `hidden` per named target. An observation is the
same word, written by the author from photographs or notes; blank means not
checked. The score counts only checked targets. Over-reported means the model
showed something the field did not; under-reported means the field saw
something the model hid.
"""

from __future__ import annotations

import pandas as pd

VISIBLE = "visible"
HIDDEN = "hidden"
_ALIASES = {
    "y": VISIBLE, "yes": VISIBLE, "v": VISIBLE, "seen": VISIBLE, "in view": VISIBLE,
    "n": HIDDEN, "no": HIDDEN, "h": HIDDEN, "not visible": HIDDEN, "unseen": HIDDEN,
}


def normalise_observed(series: pd.Series) -> pd.Series:
    """Lower-cased visible/hidden with common aliases accepted; blank becomes missing; anything else raises."""
    s = series.astype("string").str.strip().str.lower()
    s = s.mask(s == "", pd.NA).replace(_ALIASES)
    bad = s.dropna()
    bad = bad[~bad.isin([VISIBLE, HIDDEN])]
    if len(bad):
        raise ValueError(f"observed must be visible or hidden (or blank); got {sorted(set(bad))}")
    return s


def score_predictions(df: pd.DataFrame) -> dict:
    """Counts over the checked rows of a frame with `predicted` and `observed` columns."""
    if "observed" in df:
        obs = normalise_observed(df["observed"])
    else:
        obs = pd.Series(pd.NA, index=df.index, dtype="string")
    checked = df.assign(observed=obs).dropna(subset=["observed"])
    n = len(checked)
    pred = checked["predicted"].astype("string").str.lower()
    agree = int((pred == checked["observed"]).sum())
    over = int(((pred == VISIBLE) & (checked["observed"] == HIDDEN)).sum())
    under = int(((pred == HIDDEN) & (checked["observed"] == VISIBLE)).sum())
    return {
        "n_checked": n,
        "agree": agree,
        "over_reported": over,
        "under_reported": under,
        "agreement": (agree / n) if n else None,
        "status": "scored" if n else "pending",
    }


def result_sentence(score: dict, checked_against: str = "the summit photographs") -> str | None:
    """The scored line the site shows on every index; None while the field check is pending."""
    if not score["n_checked"]:
        return None
    head = f"The modeled viewshed matched {score['agree']} of {score['n_checked']} named peaks checked against {checked_against}"
    tail = []
    if score["over_reported"]:
        tail.append(f"{score['over_reported']} it showed were hidden")
    if score["under_reported"]:
        tail.append(f"{score['under_reported']} it hid were in view")
    return head + ("; " + " and ".join(tail) if tail else "") + "."
