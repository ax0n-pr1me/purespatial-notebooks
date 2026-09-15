import numpy as np
import pandas as pd
import pytest

from purespatial import peaks


def test_bearing_and_distance_north_and_east():
    az, km = peaks.bearing_distance(0.0, 0.0, [0.0, 1.0], [1.0, 0.0])
    assert abs(az[0] - 0.0) < 1e-6 and abs(km[0] - 110.574) < 0.1
    assert abs(az[1] - 90.0) < 1e-6 and abs(km[1] - 111.319) < 0.1


def _gnis():
    return pd.DataFrame(
        {
            "feature_name": ["Engineer Mountain", "Engineer Mountain", "Twilight Peak", "Coal Bank Pass", "Snowdon Peak"],
            "feature_class": ["Summit", "Summit", "Summit", "Gap", "Summit"],
            "county_name": ["San Juan", "Ouray", "San Juan", "San Juan", "San Juan"],
            "prim_lat_dec": ["37.7013", "37.9747", "37.6644", "37.6989", "37.6564"],
            "prim_long_dec": ["-107.7897", "-107.5975", "-107.7439", "-107.7742", "-107.7083"],
        }
    )


def test_normalise_maps_current_gnis_columns():
    g = peaks.normalise(_gnis())
    assert list(g.columns[:5]) == ["name", "feature_class", "county", "lat", "lon"]
    assert g["lat"].dtype.kind == "f" and len(g) == 5


def test_normalise_accepts_the_older_upper_case_vocabulary_with_elevation():
    old = pd.DataFrame(
        {"FEATURE_NAME": ["A"], "FEATURE_CLASS": ["Summit"], "PRIM_LAT_DEC": ["37.0"], "PRIM_LONG_DEC": ["-107.0"], "ELEV_IN_M": ["3900"]}
    )
    g = peaks.normalise(old)
    assert g.loc[0, "gnis_elev_m"] == 3900.0


def test_find_feature_disambiguates_namesakes_by_proximity():
    g = peaks.normalise(_gnis())
    with pytest.raises(LookupError):
        peaks.find_feature(g, "Engineer Mountain")
    s = peaks.find_feature(g, "Engineer Mountain", near=(-107.79, 37.70))
    assert s["county"] == "San Juan" and abs(s["lon"] - -107.7897) < 1e-9
    with pytest.raises(LookupError):
        peaks.find_feature(g, "Nowhere Peak")


def test_summits_near_filters_class_and_distance():
    g = peaks.normalise(_gnis())
    s = peaks.summits_near(g, -107.7897, 37.7013, max_km=10, min_km=1.0)
    assert set(s["name"]) == {"Twilight Peak", "Snowdon Peak"}
    assert (s["distance_km"] <= 10).all() and (s["distance_km"] >= 1).all()
    assert np.all((s["bearing_deg"] >= 0) & (s["bearing_deg"] < 360))
