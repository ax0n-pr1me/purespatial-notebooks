import math

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_origin

from purespatial import panorama

RES = 30.0
X0, Y0 = 250_000.0, 4_180_000.0
N = 400  # 12 km square


def _dem_with_north_wall(path):
    """Flat 3000 m plain; a 300 m wall 5 km north of the centre, spanning the full width."""
    arr = np.full((N, N), 3000.0, dtype="float32")
    wall_row = N // 2 - int(5000 / RES)
    arr[wall_row - 2 : wall_row + 1, :] = 3300.0
    with rasterio.open(
        path, "w", driver="GTiff", width=N, height=N, count=1, dtype="float32",
        crs="EPSG:32613", transform=from_origin(X0, Y0, RES, RES), nodata=-9999.0,
    ) as ds:
        ds.write(arr, 1)
    return path


def _centre_lonlat():
    x = X0 + (N / 2) * RES
    y = Y0 - (N / 2) * RES
    return Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True).transform(x, y)


def test_skyline_rises_toward_the_wall_and_falls_elsewhere(tmp_path):
    dem = _dem_with_north_wall(tmp_path / "dem.tif")
    lon, lat = _centre_lonlat()
    sky = panorama.compute_skyline(dem, lon, lat, max_distance=5800, az_step=1.0)
    assert sky.azimuth.shape == (360,)
    north = sky.skyline[0]
    south = sky.skyline[180]
    expected = math.degrees(math.atan2(300 - 1.7, 5000))
    assert abs(north - expected) < 0.6  # grid convergence and sampling
    assert south < 0
    assert abs(sky.observer_elevation - 3001.7) < 0.01


def test_peak_positions_put_a_visible_wall_top_on_the_skyline(tmp_path):
    dem = _dem_with_north_wall(tmp_path / "dem.tif")
    lon, lat = _centre_lonlat()
    sky = panorama.compute_skyline(dem, lon, lat, max_distance=5800, az_step=1.0)
    t = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True)
    wlon, wlat = t.transform(X0 + (N / 2) * RES, Y0 - (N / 2) * RES + 5000)
    az, ang = sky.peak_positions(lon, lat, [wlon], [wlat], [3300.0])
    assert abs(az[0] - 0.0) < 2.5 or abs(az[0] - 360.0) < 2.5
    assert abs(ang[0] - sky.skyline[0]) < 0.6


def test_render_writes_a_16_by_9_hero(tmp_path):
    dem = _dem_with_north_wall(tmp_path / "dem.tif")
    lon, lat = _centre_lonlat()
    sky = panorama.compute_skyline(dem, lon, lat, max_distance=5800, az_step=1.0)
    t = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True)
    wlon, wlat = t.transform(X0 + (N / 2) * RES, Y0 - (N / 2) * RES + 5000)
    peaks = pd.DataFrame({"name": ["Wall Top", "Behind"], "lon": [wlon, wlon], "lat": [wlat, wlat + 0.01], "elevation_m": [3300.0, 3100.0], "predicted": ["visible", "hidden"]})
    out = panorama.render(sky, lon, lat, peaks, tmp_path / "hero.png", band_edges_km=[0, 1, 3, 6])
    assert Image.open(out).size == (2400, 1350)
