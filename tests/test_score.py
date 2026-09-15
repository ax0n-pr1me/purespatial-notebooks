import pandas as pd
import pytest

from purespatial import score


def test_pending_when_nothing_is_observed():
    df = pd.DataFrame({"predicted": ["visible", "hidden"], "observed": ["", None]})
    s = score.score_predictions(df)
    assert s["status"] == "pending" and s["n_checked"] == 0 and s["agreement"] is None
    assert score.result_sentence(s) is None


def test_counts_agreement_over_and_under_reporting_and_accepts_aliases():
    df = pd.DataFrame(
        {
            "predicted": ["visible", "visible", "hidden", "hidden", "visible"],
            "observed": ["yes", "hidden", "Visible", "n", ""],
        }
    )
    s = score.score_predictions(df)
    assert (s["n_checked"], s["agree"], s["over_reported"], s["under_reported"]) == (4, 2, 1, 1)
    assert s["status"] == "scored" and abs(s["agreement"] - 0.5) < 1e-9
    assert score.result_sentence(s) == (
        "The modeled viewshed matched 2 of 4 named peaks checked against the summit photographs; "
        "1 it showed were hidden and 1 it hid were in view."
    )


def test_perfect_agreement_has_no_tail():
    df = pd.DataFrame({"predicted": ["visible", "hidden"], "observed": ["visible", "hidden"]})
    s = score.score_predictions(df)
    assert score.result_sentence(s, "the photographs") == "The modeled viewshed matched 2 of 2 named peaks checked against the photographs."


def test_unknown_observation_word_is_refused():
    df = pd.DataFrame({"predicted": ["visible"], "observed": ["maybe"]})
    with pytest.raises(ValueError):
        score.score_predictions(df)


def test_missing_observed_column_is_pending():
    s = score.score_predictions(pd.DataFrame({"predicted": ["visible"]}))
    assert s["status"] == "pending"
