# ---
# jupyter:
#   jupytext:
#     formats: py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # A 3DEP viewshed from the Engineer Mountain summit
#
# What can be seen from the summit of Engineer Mountain (San Juan County, Colorado), according to the
# USGS 3D Elevation Program, and how well does that match what the summit photographs show?
#
# Two elevation models, both public domain: the 1/3 arc-second seamless DEM resampled to 30 m for a
# 60 km far field, and the 1 m lidar bare-earth DEM for a 3 km near field. `gdal_viewshed` computes
# visibility from an observer standing 1.7 m above the summit cell, with Earth curvature and standard
# refraction. Named summits come from the USGS Geographic Names Information System; the model rates each
# one visible or hidden, and the author marks each from the photographs in `field/observations.csv`.
# The score is the agreement between the two lists.

# %%
from pathlib import Path

import numpy as np
import pandas as pd
from params import (
    DATASETS,
    FAR_RADIUS_M,
    FAR_RES_M,
    MAX_PEAKS,
    MIN_PEAK_DISTANCE_KM,
    MIN_PEAK_ELEVATION_M,
    NEAR_HINT,
    NEAR_RADIUS_M,
    NEAR_RES_M,
    OBSERVER_HEIGHT_M,
    REGION,
    SLUG,
    STATE,
    SUBJECT_NAME,
)

import purespatial as ps

HERE = Path.cwd()  # `make run` executes the notebook inside the post folder
DATA, FIG, FIELD = HERE / "data", HERE / "figures", HERE / "field"
for d in (DATA, FIG, FIELD / "photos"):
    d.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## Subject
#
# GNIS carries two Colorado summits named Engineer Mountain. The hint in `params.py` selects the one above
# Coal Bank Pass.

# %%
gnis = ps.peaks.load_gnis(STATE, DATA)
summit = ps.peaks.find_feature(gnis, SUBJECT_NAME, near=NEAR_HINT)
LON, LAT = float(summit["lon"]), float(summit["lat"])
print(f"{summit['name']}, {summit['county']} County: {LAT:.5f} N, {abs(LON):.5f} W")

# %% [markdown]
# ## Elevation models
#
# Both grids are projected to UTM zone 13N (metres) so distances and the viewshed radius are in metres.

# %%
far_dem = ps.dem.fetch_dem(LON, LAT, FAR_RADIUS_M, FAR_RES_M, DATA / f"dem_{FAR_RES_M}m_{FAR_RADIUS_M // 1000}km.tif")
near_dem = ps.dem.fetch_dem(LON, LAT, NEAR_RADIUS_M, NEAR_RES_M, DATA / f"dem_{NEAR_RES_M}m_{NEAR_RADIUS_M // 1000}km.tif")
far_info, near_info = ps.dem.info(far_dem), ps.dem.info(near_dem)
summit_elev_near = float(ps.dem.sample(near_dem, LON, LAT)[0])
summit_elev_far = float(ps.dem.sample(far_dem, LON, LAT)[0])
print(f"far field  {far_info['width']} x {far_info['height']} cells at {far_info['resolution_m']:g} m")
print(f"near field {near_info['width']} x {near_info['height']} cells at {near_info['resolution_m']:g} m")
print(f"summit elevation: {summit_elev_near:.1f} m in the 1 m DEM, {summit_elev_far:.1f} m in the 30 m DEM")

# %% [markdown]
# ## Viewsheds
#
# `gdal_viewshed`, observer 1.7 m above the summit cell, target height 0 (the ground), curvature
# coefficient 0.85714 (curvature with standard refraction). The far run is cut at 60 km, the near run at 3 km.

# %%
far_vs = ps.viewshed.run_viewshed(
    far_dem, LON, LAT, DATA / "viewshed_far.tif", observer_height=OBSERVER_HEIGHT_M, max_distance=FAR_RADIUS_M
)
near_vs = ps.viewshed.run_viewshed(
    near_dem, LON, LAT, DATA / "viewshed_near.tif", observer_height=OBSERVER_HEIGHT_M, max_distance=NEAR_RADIUS_M
)
print(f"visible share of the far field:  {ps.viewshed.visible_fraction(far_vs):.1%}")
print(f"visible share of the near field: {ps.viewshed.visible_fraction(near_vs):.1%}")

# %% [markdown]
# ## Named peaks the model rates visible or hidden
#
# Every GNIS summit within 60 km whose DEM elevation is at least 3600 m, the highest forty, each sampled
# against the far viewshed at its own coordinates.

# %%
cand = ps.peaks.summits_near(gnis, LON, LAT, max_km=FAR_RADIUS_M / 1000, min_km=MIN_PEAK_DISTANCE_KM)
cand["elevation_m"] = ps.dem.sample(far_dem, cand["lon"], cand["lat"])
cand = cand.dropna(subset=["elevation_m"])
cand = cand[cand["elevation_m"] >= MIN_PEAK_ELEVATION_M]
cand = cand.sort_values("elevation_m", ascending=False).drop_duplicates("name").head(MAX_PEAKS)
vis = ps.dem.sample(far_vs, cand["lon"], cand["lat"])
cand["predicted"] = np.where(np.nan_to_num(vis, nan=0.0) >= 128, "visible", "hidden")
peaks = cand.sort_values("bearing_deg").reset_index(drop=True)
n_vis = int((peaks["predicted"] == "visible").sum())
farthest = peaks[peaks["predicted"] == "visible"]["distance_km"].max()
print(f"{len(peaks)} named peaks rated: {n_vis} visible, {len(peaks) - n_vis} hidden; farthest visible {farthest:.1f} km")
peaks[["name", "county", "elevation_m", "distance_km", "bearing_deg", "predicted"]].round({"elevation_m": 0, "distance_km": 1, "bearing_deg": 0})

# %% [markdown]
# ## Field check
#
# `field/observations.csv` is written once, with the model's rating per peak and an empty `observed`
# column. The author fills `observed` (visible or hidden) from the summit photographs and names the photo.
# Filled rows are never overwritten. The score below counts only filled rows.

# %%
OBS = FIELD / "observations.csv"
cols = ["name", "county", "lat", "lon", "elevation_m", "distance_km", "bearing_deg", "predicted", "observed", "photo", "note"]
if not OBS.exists():
    template = peaks.assign(observed="", photo="", note="")[cols].round(
        {"lat": 5, "lon": 5, "elevation_m": 0, "distance_km": 1, "bearing_deg": 0}
    )
    template.to_csv(OBS, index=False)
    print(f"wrote {OBS.relative_to(HERE)} with {len(template)} rows to fill")
obs = pd.read_csv(OBS, dtype={"observed": "string", "photo": "string", "note": "string"}, keep_default_na=False)
merged = peaks.merge(obs[["name", "observed", "photo", "note"]], on="name", how="left")
score = ps.score.score_predictions(merged)
sentence = ps.score.result_sentence(score)
print(score)
print(sentence or "field check pending: fill field/observations.csv and re-run")

# %% [markdown]
# ## Figures

# %%
by_height = peaks.sort_values("elevation_m", ascending=False)
far_png = ps.figures.viewshed_map(
    far_dem, far_vs, (LON, LAT), by_height, FIG / "far-field.png", label_top=20,
    title=f"Modeled visibility from the {SUBJECT_NAME} summit. 3DEP 1/3 arc-second DEM at {FAR_RES_M} m, {FAR_RADIUS_M // 1000} km radius.",
)
near_png = ps.figures.viewshed_map(
    near_dem, near_vs, (LON, LAT), None, FIG / "near-field.png",
    title=f"Near field. 3DEP {NEAR_RES_M} m lidar bare-earth DEM, {NEAR_RADIUS_M // 1000} km radius.",
)
hero_png = ps.figures.hero_map(far_dem, far_vs, (LON, LAT), by_height.head(12), FIG / "hero.png")
[p.name for p in (far_png, near_png, hero_png)]

# %% [markdown]
# ![Modeled visibility from the summit over 60 km at 30 m; filled marks are peaks the model rates visible, hollow marks hidden](figures/far-field.png)
#
# ![Near field on the 1 m lidar bare-earth DEM, 3 km](figures/near-field.png)

# %% [markdown]
# ## Result

# %%
figures = [
    {
        "file": "figures/far-field.png",
        "alt": f"Viewshed from the {SUBJECT_NAME} summit over a hillshade of the San Juan Mountains, visible ground tinted green, named peaks marked visible or hidden.",
        "caption": f"Modeled visibility from the summit at {FAR_RES_M} m over {FAR_RADIUS_M // 1000} km: {n_vis} of {len(peaks)} named peaks rated visible.",
    },
    {
        "file": "figures/near-field.png",
        "alt": f"Near-field viewshed from the {SUBJECT_NAME} summit on the 1 m lidar bare-earth DEM, 3 km radius.",
        "caption": "The 1 m bare-earth model removes the trees, so near ridgelines below treeline may show as visible when they are not.",
    },
    {"file": "figures/hero.png", "alt": f"Viewshed from the {SUBJECT_NAME} summit over a hillshade, framed wide.", "caption": "Hero."},
]
ps.result.write_result(
    HERE / "result.json",
    slug=SLUG,
    subject={"name": SUBJECT_NAME, "kind": "landscape", "region": REGION, "lat": LAT, "lon": LON, "county": summit["county"], "elevation_m_1m_dem": summit_elev_near},
    datasets=DATASETS,
    method={
        "tool": "gdal_viewshed",
        "observer_height_m": OBSERVER_HEIGHT_M,
        "target_height_m": 0.0,
        "curvature_coefficient": ps.viewshed.CURVATURE,
        "far_field": {**far_info, "radius_m": FAR_RADIUS_M, "product": "3DEP 1/3 arc-second seamless DEM, resampled"},
        "near_field": {**near_info, "radius_m": NEAR_RADIUS_M, "product": "3DEP 1 m lidar bare-earth DEM"},
        "peaks": {"source": "USGS GNIS DomesticNames (Summit)", "min_elevation_m": MIN_PEAK_ELEVATION_M, "max_count": MAX_PEAKS},
        "visible_fraction": {"far": ps.viewshed.visible_fraction(far_vs), "near": ps.viewshed.visible_fraction(near_vs)},
    },
    predictions=peaks[["name", "county", "lat", "lon", "elevation_m", "distance_km", "bearing_deg", "predicted"]].round(
        {"lat": 5, "lon": 5, "elevation_m": 0, "distance_km": 1, "bearing_deg": 0}
    ).to_dict("records"),
    field_check={"status": score["status"], "file": "field/observations.csv", "photos": "field/photos/", "checked_against": "the summit photographs"},
    score=score if score["n_checked"] else None,
    result=sentence,
    findings=[],
    figures=figures,
)
print("wrote result.json:", score["status"])
