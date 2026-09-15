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
    HERO,
    MAX_PEAKS,
    MIN_PEAK_DISTANCE_KM,
    MIN_PEAK_ELEVATION_M,
    NEAR_HINT,
    NEAR_RADIUS_M,
    NEAR_RES_M,
    OBSERVER_HEIGHT_M,
    REGION,
    SLUG,
    SNAP_RADIUS_M,
    STATE,
    STYLE,
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
gnis_elev_near = float(ps.dem.sample(near_dem, LON, LAT)[0])
print(f"far field  {far_info['width']} x {far_info['height']} cells at {far_info['resolution_m']:g} m")
print(f"near field {near_info['width']} x {near_info['height']} cells at {near_info['resolution_m']:g} m")
print(f"1 m DEM at the GNIS point: {gnis_elev_near:.1f} m")

# %% [markdown]
# ### The observer stands on the crest, not on the gazetteer point
#
# GNIS places a summit to the nearest few tens of metres. On a 1 m grid that is the difference between
# the crest and the slope below it, and a viewshed from the slope is hidden by the summit itself (the
# first run of this notebook saw nothing to the north within 3 km). The observer therefore moves to the
# highest 1 m cell within `SNAP_RADIUS_M` of the GNIS point, and both viewsheds use that cell.

# %%
OBS_LON, OBS_LAT, summit_elev_near = ps.dem.highest_point(near_dem, LON, LAT, SNAP_RADIUS_M)
_, snap_km = ps.peaks.bearing_distance(LON, LAT, [OBS_LON], [OBS_LAT])
summit_elev_far = float(ps.dem.sample(far_dem, OBS_LON, OBS_LAT)[0])
print(f"observer: {OBS_LAT:.5f} N, {abs(OBS_LON):.5f} W, {snap_km[0] * 1000:.0f} m from the GNIS point")
print(f"summit elevation: {summit_elev_near:.1f} m in the 1 m DEM, {summit_elev_far:.1f} m in the 30 m DEM")

# %% [markdown]
# ## Viewsheds
#
# `gdal_viewshed`, observer 1.7 m above the summit cell, target height 0 (the ground), curvature
# coefficient 0.85714 (curvature with standard refraction). The far run is cut at 60 km, the near run at 3 km.

# %%
far_vs = ps.viewshed.run_viewshed(
    far_dem, OBS_LON, OBS_LAT, DATA / "viewshed_far.tif", observer_height=OBSERVER_HEIGHT_M, max_distance=FAR_RADIUS_M
)
near_vs = ps.viewshed.run_viewshed(
    near_dem, OBS_LON, OBS_LAT, DATA / "viewshed_near.tif", observer_height=OBSERVER_HEIGHT_M, max_distance=NEAR_RADIUS_M
)
print(f"visible share of the far field:  {ps.viewshed.visible_fraction(far_vs):.1%}")
print(f"visible share of the near field: {ps.viewshed.visible_fraction(near_vs):.1%}")

# %% [markdown]
# ## Named peaks the model rates visible or hidden
#
# Every GNIS summit within 60 km whose DEM elevation is at least 3600 m, the highest forty, each sampled
# against the far viewshed at its own coordinates.

# %%
cand = ps.peaks.summits_near(gnis, OBS_LON, OBS_LAT, max_km=FAR_RADIUS_M / 1000, min_km=MIN_PEAK_DISTANCE_KM)
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
# The same table as points for QGIS or GitHub's map view, with the observer as one more feature.

# %%
import geopandas as gpd

pts = peaks[["name", "county", "elevation_m", "distance_km", "bearing_deg", "predicted", "lon", "lat"]].round(
    {"elevation_m": 0, "distance_km": 1, "bearing_deg": 0, "lon": 5, "lat": 5}
)
observer_row = pd.DataFrame([{"name": SUBJECT_NAME, "county": summit["county"], "elevation_m": round(summit_elev_near), "distance_km": 0.0, "bearing_deg": 0.0, "predicted": "observer", "lon": round(OBS_LON, 5), "lat": round(OBS_LAT, 5)}])
pts = pd.concat([observer_row, pts], ignore_index=True)
gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326").to_file(HERE / "peaks.geojson", driver="GeoJSON")
print("wrote peaks.geojson with", len(pts), "features")

# %% [markdown]
# ## Field check
#
# `field/observations.csv` has one row per rated peak. The model's columns (`predicted`, elevation,
# distance, bearing) are refreshed on every run; the author's columns (`observed`, `photo`, `note`) are
# read from the existing file and written back untouched, so a re-run never loses a mark. The author
# fills `observed` (visible or hidden) from the summit photographs. The score counts only filled rows.

# %%
OBS = FIELD / "observations.csv"
AUTHOR_COLS = ["observed", "photo", "note"]
cols = ["name", "county", "lat", "lon", "elevation_m", "distance_km", "bearing_deg", "predicted", *AUTHOR_COLS]
model_rows = peaks.round({"lat": 5, "lon": 5, "elevation_m": 0, "distance_km": 1, "bearing_deg": 0})
if OBS.exists():
    previous = pd.read_csv(OBS, dtype=str, keep_default_na=False)
    kept = previous[["name", *AUTHOR_COLS]]
    flipped = model_rows.merge(previous[["name", "predicted"]].rename(columns={"predicted": "was"}), on="name", how="left")
    flipped = flipped[(flipped["was"] != "") & (flipped["was"].notna()) & (flipped["was"] != flipped["predicted"])]
    if len(flipped):
        print(f"{len(flipped)} ratings changed since the last run:")
        print(flipped[["name", "was", "predicted"]].to_string(index=False))
else:
    kept = pd.DataFrame({"name": model_rows["name"], "observed": "", "photo": "", "note": ""})
table = model_rows.merge(kept, on="name", how="left").fillna({"observed": "", "photo": "", "note": ""})[cols]
table.to_csv(OBS, index=False)
print(f"wrote {OBS.relative_to(HERE)}: {len(table)} rows, {(table['observed'] != '').sum()} observed")
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
    far_dem, far_vs, (OBS_LON, OBS_LAT), by_height, FIG / "far-field.png", style=STYLE,
    title=f"Modeled visibility from the {SUBJECT_NAME} summit. 3DEP 1/3 arc-second DEM at {FAR_RES_M} m, {FAR_RADIUS_M // 1000} km radius.",
)
from dataclasses import replace

NEAR_STYLE = replace(STYLE, contours_m=50, contour_labels=True, max_raster_px=4000)
near_png = ps.figures.viewshed_map(
    near_dem, near_vs, (OBS_LON, OBS_LAT), None, FIG / "near-field.png", style=NEAR_STYLE,
    title=f"Near field. 3DEP {NEAR_RES_M} m lidar bare-earth DEM, {NEAR_RADIUS_M // 1000} km radius, 50 m contours.",
)

# %% [markdown]
# ### The view itself
#
# A skyline panorama cast from the observer: rays every 0.05 degrees of true azimuth, the DEM sampled
# every 30 m out to 60 km, the same curvature and refraction as the viewshed, the eye 1.7 m above the 1 m crest.
# Distance bands are drawn far
# to near, so nearer ridges hide farther ones exactly as they do from the summit. Peaks rated visible
# stand on the skyline; peaks rated hidden fall inside the ridge that hides them.

# %%
sky = ps.panorama.compute_skyline(
    far_dem, OBS_LON, OBS_LAT, observer_height=OBSERVER_HEIGHT_M, max_distance=FAR_RADIUS_M, observer_elevation=summit_elev_near
)
pano_png = ps.panorama.render(
    sky, OBS_LON, OBS_LAT, peaks, FIG / "panorama.png", style=STYLE,
    title=f"The skyline from the {SUBJECT_NAME} summit, north to south over east (top) and south to north over west (bottom). 3DEP, 60 km.",
)
print(f"skyline: {np.nanmin(sky.skyline):.1f} to {np.nanmax(sky.skyline):.1f} degrees; observer {sky.observer_elevation:.1f} m with eye height")

# %% [markdown]
# ### Hero candidates
#
# Several renderings of the same result; `HERO` in `params.py` picks the one copied to `figures/hero.png`.

# %%
import shutil

candidates = {
    # the 1 m lidar surface with the whole 3 km viewshed disc, 6.4 km wide, 50 m contours
    "relief": ps.figures.hero_map(near_dem, near_vs, (OBS_LON, OBS_LAT), None, FIG / "hero-relief.png", style=replace(STYLE, contours_m=50), width_m=6400, max_px=2400),
    # the summit close up, 3.2 km wide, native 1 m pixels
    "relief-tight": ps.figures.hero_map(near_dem, near_vs, (OBS_LON, OBS_LAT), None, FIG / "hero-relief-tight.png", style=replace(STYLE, contours_m=50), width_m=3200, max_px=2400),
    # the wide surface without contours
    "relief-plain": ps.figures.hero_map(near_dem, near_vs, (OBS_LON, OBS_LAT), None, FIG / "hero-relief-plain.png", style=STYLE, width_m=6400, max_px=2400),
    # the skyline as seen from the summit
    "panorama": ps.panorama.render(sky, OBS_LON, OBS_LAT, peaks, FIG / "hero-panorama.png", style=STYLE),
    # the 60 km map, light and dark
    "map": ps.figures.hero_map(far_dem, far_vs, (OBS_LON, OBS_LAT), by_height, FIG / "hero-map.png", style=STYLE),
    "map-dark": ps.figures.hero_map(far_dem, far_vs, (OBS_LON, OBS_LAT), by_height, FIG / "hero-map-dark.png", style=replace(STYLE, dark=True, sightlines=True)),
}
hero_png = FIG / "hero.png"
shutil.copyfile(candidates[HERO], hero_png)
print("hero:", HERO)
[p.name for p in (far_png, near_png, pano_png, *candidates.values(), hero_png)]

# %% [markdown]
# ![Modeled visibility from the summit over 60 km at 30 m; filled marks are peaks the model rates visible, hollow marks hidden](figures/far-field.png)
#
# ![Near field on the 1 m lidar bare-earth DEM, 3 km](figures/near-field.png)
#
# ![The skyline from the summit, peaks rated visible on the ridge line and hidden peaks inside the ridges that hide them](figures/panorama.png)

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
    {
        "file": "figures/panorama.png",
        "alt": f"Skyline panorama from the {SUBJECT_NAME} summit in two half-turns, ridges shaded by distance, named peaks marked visible on the skyline or hidden inside the ridges.",
        "caption": f"The skyline the model computes from the summit; peaks rated visible stand on it, {len(peaks) - n_vis} rated hidden sit behind nearer ridges.",
    },
    {"file": "figures/hero.png", "alt": f"Skyline panorama from the {SUBJECT_NAME} summit, ridges shaded by distance, named peaks marked.", "caption": "Hero."},
]
ps.result.write_result(
    HERE / "result.json",
    slug=SLUG,
    subject={
        "name": SUBJECT_NAME, "kind": "landscape", "region": REGION, "county": summit["county"],
        "gnis": {"lat": LAT, "lon": LON, "elevation_m_1m_dem": gnis_elev_near},
        "observer": {"lat": OBS_LAT, "lon": OBS_LON, "elevation_m_1m_dem": summit_elev_near, "snapped_within_m": SNAP_RADIUS_M, "moved_m": float(snap_km[0] * 1000)},
    },
    datasets=DATASETS,
    method={
        "tool": "gdal_viewshed",
        "observer_height_m": OBSERVER_HEIGHT_M,
        "observer_snapped_to_highest_cell_within_m": SNAP_RADIUS_M,
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
