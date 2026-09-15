import numpy as np
import rasterio
from rasterio.transform import from_origin

from purespatial import dem


def test_utm_zone_for_the_san_juans_is_13_north():
    assert dem.utm_crs_for(-107.79, 37.70).to_epsg() == 32613
    assert dem.utm_crs_for(-122.4, 37.8).to_epsg() == 32610
    assert dem.utm_crs_for(151.2, -33.9).to_epsg() == 32756


def test_bbox_is_centred_and_wider_in_longitude_at_high_latitude():
    w, s, e, n = dem.bbox_around(-107.79, 37.70, 10_000)
    assert abs(((w + e) / 2) - -107.79) < 1e-9
    assert abs(((s + n) / 2) - 37.70) < 1e-9
    assert (e - w) > (n - s)
    assert abs((n - s) - 2 * 10_000 / 111_320) < 1e-9


def _write_raster(path, arr, res=10.0, x0=250_000.0, y0=4_180_000.0, nodata=-9999.0):
    h, w = arr.shape
    with rasterio.open(
        path, "w", driver="GTiff", width=w, height=h, count=1, dtype="float32",
        crs="EPSG:32613", transform=from_origin(x0, y0, res, res), nodata=nodata,
    ) as ds:
        ds.write(arr.astype("float32"), 1)
    return path


def test_sample_reads_values_and_returns_nan_off_raster_and_on_nodata(tmp_path):
    arr = np.full((20, 20), 3000.0)
    arr[5, 5] = -9999.0
    arr[10, 10] = 3456.0
    path = _write_raster(tmp_path / "d.tif", arr)
    with rasterio.open(path) as ds:
        centre_x, centre_y = ds.xy(10, 10)
        nod_x, nod_y = ds.xy(5, 5)
    from pyproj import Transformer

    t = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True)
    (lon_c, lat_c) = t.transform(centre_x, centre_y)
    (lon_n, lat_n) = t.transform(nod_x, nod_y)
    vals = dem.sample(path, [lon_c, lon_n, -100.0], [lat_c, lat_n, 30.0])
    assert vals[0] == 3456.0
    assert np.isnan(vals[1])
    assert np.isnan(vals[2])


def test_info_reports_grid(tmp_path):
    path = _write_raster(tmp_path / "d.tif", np.zeros((4, 6)))
    i = dem.info(path)
    assert (i["width"], i["height"], i["resolution_m"]) == (6, 4, 10.0)
    assert i["crs"] == "EPSG:32613"


def test_highest_point_snaps_to_the_crest_within_radius(tmp_path):
    arr = np.full((40, 40), 3000.0)
    arr[10, 30] = 3950.0  # a summit 20 cells (200 m) east of the query point at (10, 10)
    arr[12, 13] = 3900.0  # a lower crest 3 cells (~36 m) away
    path = _write_raster(tmp_path / "d.tif", arr)
    from pyproj import Transformer

    with rasterio.open(path) as ds:
        qx, qy = ds.xy(10, 10)
    lon, lat = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True).transform(qx, qy)
    plon, _plat, elev = dem.highest_point(path, lon, lat, radius_m=60)
    assert elev == 3900.0
    plon2, _plat2, elev2 = dem.highest_point(path, lon, lat, radius_m=300)
    assert elev2 == 3950.0 and abs(plon2 - lon) > abs(plon - lon)
