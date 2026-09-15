import shutil

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from purespatial import viewshed

pytestmark = pytest.mark.skipif(shutil.which("gdal_viewshed") is None, reason="gdal_viewshed not installed")

RES = 10.0
X0, Y0 = 250_000.0, 4_180_000.0


def _dem_with_ridge(path):
    """A flat 3000 m plain, 200 by 200 cells, with a 100 m wall across row 60 (north of the observer)."""
    arr = np.full((200, 200), 3000.0, dtype="float32")
    arr[60:63, :] = 3100.0
    with rasterio.open(
        path, "w", driver="GTiff", width=200, height=200, count=1, dtype="float32",
        crs="EPSG:32613", transform=from_origin(X0, Y0, RES, RES), nodata=-9999.0,
    ) as ds:
        ds.write(arr, 1)
    return path


def _lonlat(row, col):
    x = X0 + (col + 0.5) * RES
    y = Y0 - (row + 0.5) * RES
    return Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True).transform(x, y)


def test_wall_hides_the_far_side_and_not_the_near_side(tmp_path):
    dem = _dem_with_ridge(tmp_path / "dem.tif")
    lon, lat = _lonlat(120, 100)  # observer south of the wall
    out = viewshed.run_viewshed(dem, lon, lat, tmp_path / "vs.tif", observer_height=1.7)
    with rasterio.open(out) as ds:
        vs = ds.read(1)
        # observer at row 120: rows 64..119 (between observer and wall) visible; rows 0..59 (beyond) hidden
        r_near, c_near = ds.index(*Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(*_lonlat(100, 100)))
        r_far, c_far = ds.index(*Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(*_lonlat(20, 100)))
    assert vs[r_near, c_near] == 255
    assert vs[r_far, c_far] == 0
    assert 0.0 < viewshed.visible_fraction(out) < 1.0


def test_cached_output_is_reused(tmp_path):
    dem = _dem_with_ridge(tmp_path / "dem.tif")
    lon, lat = _lonlat(120, 100)
    out = viewshed.run_viewshed(dem, lon, lat, tmp_path / "vs.tif")
    stamp = out.stat().st_mtime_ns
    again = viewshed.run_viewshed(dem, lon, lat, tmp_path / "vs.tif")
    assert again == out and again.stat().st_mtime_ns == stamp


def test_observer_outside_the_dem_is_refused(tmp_path):
    dem = _dem_with_ridge(tmp_path / "dem.tif")
    with pytest.raises(ValueError):
        viewshed.run_viewshed(dem, -100.0, 30.0, tmp_path / "vs.tif")
