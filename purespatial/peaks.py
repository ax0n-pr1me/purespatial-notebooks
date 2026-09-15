"""Named summits from the USGS Geographic Names Information System (GNIS), public domain.

GNIS ships one pipe-delimited text file per state (the "Domestic Names"
staged product on The National Map). It carries names, feature classes, and
coordinates; the current format carries no elevation, so elevations are
sampled from the DEM. The zip is cached in the post's data/ folder.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pyproj import Geod

GNIS_URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/DomesticNames_{state}_Text.zip"
_GEOD = Geod(ellps="WGS84")


def load_gnis(state: str, cache_dir: str | Path) -> pd.DataFrame:
    """All GNIS features for a state as name, feature_class, county, lat, lon (and gnis_elev_m when present)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    zpath = cache_dir / f"DomesticNames_{state.upper()}_Text.zip"
    if not zpath.exists():
        r = requests.get(GNIS_URL.format(state=state.upper()), timeout=180)
        r.raise_for_status()
        zpath.write_bytes(r.content)
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        raw = z.read(name).decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(raw), sep="|", dtype=str, on_bad_lines="skip")
    return normalise(df)


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Map either GNIS column vocabulary (current lower-case or the older upper-case national file) to one shape."""
    cols = {c.strip().lower(): c for c in df.columns}

    def pick(*names: str) -> str:
        for n in names:
            if n in cols:
                return cols[n]
        raise KeyError(f"GNIS file has none of {names}; columns start {list(df.columns)[:8]}")

    out = pd.DataFrame(
        {
            "name": df[pick("feature_name")].astype(str).str.strip(),
            "feature_class": df[pick("feature_class")].astype(str).str.strip(),
            "county": df[cols["county_name"]].astype(str).str.strip() if "county_name" in cols else "",
            "lat": pd.to_numeric(df[pick("prim_lat_dec")], errors="coerce"),
            "lon": pd.to_numeric(df[pick("prim_long_dec")], errors="coerce"),
        }
    )
    if "elev_in_m" in cols:
        out["gnis_elev_m"] = pd.to_numeric(df[cols["elev_in_m"]], errors="coerce")
    return out.dropna(subset=["lat", "lon"]).reset_index(drop=True)


def bearing_distance(lon0: float, lat0: float, lons, lats) -> tuple[np.ndarray, np.ndarray]:
    """Forward azimuth in degrees (0 to 360) and geodesic distance in km from one point to many."""
    lons = np.atleast_1d(np.asarray(lons, dtype=float))
    lats = np.atleast_1d(np.asarray(lats, dtype=float))
    az, _, dist = _GEOD.inv(np.full(lons.shape, lon0), np.full(lats.shape, lat0), lons, lats)
    return np.mod(az, 360.0), dist / 1000.0


def summits_near(gnis: pd.DataFrame, lon: float, lat: float, max_km: float, min_km: float = 1.0) -> pd.DataFrame:
    """GNIS summits between min_km and max_km of the observer, with bearing_deg and distance_km."""
    s = gnis[gnis["feature_class"].str.lower() == "summit"].copy()
    s["bearing_deg"], s["distance_km"] = bearing_distance(lon, lat, s["lon"], s["lat"])
    s = s[(s["distance_km"] >= min_km) & (s["distance_km"] <= max_km)]
    return s.sort_values("distance_km").reset_index(drop=True)


def find_feature(gnis: pd.DataFrame, name: str, near: tuple[float, float] | None = None, feature_class: str = "Summit") -> pd.Series:
    """One GNIS feature by exact name; `near=(lon, lat)` picks among namesakes."""
    m = gnis[(gnis["name"].str.lower() == name.lower()) & (gnis["feature_class"].str.lower() == feature_class.lower())]
    if m.empty:
        raise LookupError(f"no GNIS {feature_class} named {name!r}")
    if len(m) > 1:
        if near is None:
            raise LookupError(f"{len(m)} GNIS features named {name!r}; pass near=(lon, lat)")
        _, d = bearing_distance(near[0], near[1], m["lon"], m["lat"])
        m = m.assign(_d=d).sort_values("_d").drop(columns="_d")
    return m.iloc[0]
