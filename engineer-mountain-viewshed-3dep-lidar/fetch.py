"""Download this post's public inputs into data/ (gitignored). The notebook makes the same calls; run this first on a fresh clone."""

from pathlib import Path

from params import FAR_RADIUS_M, FAR_RES_M, NEAR_HINT, NEAR_RADIUS_M, NEAR_RES_M, STATE, SUBJECT_NAME

import purespatial as ps

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

gnis = ps.peaks.load_gnis(STATE, DATA)
summit = ps.peaks.find_feature(gnis, SUBJECT_NAME, near=NEAR_HINT)
lon, lat = float(summit["lon"]), float(summit["lat"])
print(f"{SUBJECT_NAME}, {summit['county']} County: {lat:.5f}, {lon:.5f}")

far = ps.dem.fetch_dem(lon, lat, FAR_RADIUS_M, FAR_RES_M, DATA / f"dem_{FAR_RES_M}m_{FAR_RADIUS_M // 1000}km.tif")
print("far field:", ps.dem.info(far))
near = ps.dem.fetch_dem(lon, lat, NEAR_RADIUS_M, NEAR_RES_M, DATA / f"dem_{NEAR_RES_M}m_{NEAR_RADIUS_M // 1000}km.tif")
print("near field:", ps.dem.info(near))
print("inputs ready in", DATA)
