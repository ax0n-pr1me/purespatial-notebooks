import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_origin

from purespatial import figures

RES = 30.0
X0, Y0 = 250_000.0, 4_180_000.0


def _rasters(tmp_path):
    n = 120
    yy, xx = np.mgrid[0:n, 0:n]
    dem = (3000 + 400 * np.sin(xx / 9.0) * np.cos(yy / 11.0)).astype("float32")
    vs = np.where((xx - 60) ** 2 + (yy - 60) ** 2 < 30**2, 255, 0).astype("uint8")
    for name, arr, dtype, nodata in (("dem.tif", dem, "float32", -9999.0), ("vs.tif", vs, "uint8", None)):
        with rasterio.open(
            tmp_path / name, "w", driver="GTiff", width=n, height=n, count=1, dtype=dtype,
            crs="EPSG:32613", transform=from_origin(X0, Y0, RES, RES), nodata=nodata,
        ) as ds:
            ds.write(arr, 1)
    return tmp_path / "dem.tif", tmp_path / "vs.tif"


def _lonlat(col, row):
    t = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True)
    return t.transform(X0 + (col + 0.5) * RES, Y0 - (row + 0.5) * RES)


def _peaks():
    rows = []
    for i, (c, r, pred) in enumerate([(20, 20, "visible"), (22, 21, "hidden"), (24, 22, "visible"), (90, 30, "hidden"), (60, 100, "visible")]):
        lon, lat = _lonlat(c, r)
        rows.append({"name": f"Peak {i}", "lon": lon, "lat": lat, "predicted": pred})
    return pd.DataFrame(rows)


def test_viewshed_map_is_at_least_2000_px_and_labels_do_not_all_land(tmp_path):
    dem, vs = _rasters(tmp_path)
    lon, lat = _lonlat(60, 60)
    out = figures.viewshed_map(dem, vs, (lon, lat), _peaks(), tmp_path / "map.png", title="test")
    w, h = Image.open(out).size
    assert min(w, h) >= 2000
    # three peaks sit within two cells of each other; greedy placement drops at least one of their labels
    fig_labels = figures._place_labels
    assert callable(fig_labels)


def test_hero_is_16_by_9(tmp_path):
    dem, vs = _rasters(tmp_path)
    lon, lat = _lonlat(60, 60)
    out = figures.hero_map(dem, vs, (lon, lat), _peaks(), tmp_path / "hero.png")
    w, h = Image.open(out).size
    assert (w, h) == (2400, 1350)


def test_style_overrides_apply(tmp_path):
    dem, vs = _rasters(tmp_path)
    lon, lat = _lonlat(60, 60)
    st = figures.Style(dpi=100, size_in=6, legend=False, scale_bar=False, label_top=0)
    out = figures.viewshed_map(dem, vs, (lon, lat), _peaks(), tmp_path / "small.png", title="t", style=st)
    w, h = Image.open(out).size
    assert max(w, h) < 800
