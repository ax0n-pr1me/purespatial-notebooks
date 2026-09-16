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


def _wall_peaks():
    t = Transformer.from_crs("EPSG:32613", "EPSG:4326", always_xy=True)
    wlon, wlat = t.transform(X0 + (N / 2) * RES, Y0 - (N / 2) * RES + 5000)
    return pd.DataFrame({
        "name": ["Wall Top", "Behind the Wall"],
        "lon": [wlon, wlon],
        "lat": [wlat, wlat + 0.01],
        "elevation_m": [3300.0, 3100.0],
        "predicted": ["visible", "hidden"],
    })


def _sky(tmp_path):
    dem = _dem_with_north_wall(tmp_path / "dem.tif")
    lon, lat = _centre_lonlat()
    return panorama.compute_skyline(dem, lon, lat, max_distance=5800, az_step=1.0), lon, lat


def test_skyline_rises_toward_the_wall_and_falls_elsewhere(tmp_path):
    sky, _, _ = _sky(tmp_path)
    assert sky.azimuth.shape == (360,)
    north = sky.skyline[0]
    south = sky.skyline[180]
    expected = math.degrees(math.atan2(300 - 1.7, 5000))
    assert abs(north - expected) < 0.6  # grid convergence and sampling
    assert south < 0
    assert abs(sky.observer_elevation - 3001.7) < 0.01


def test_peak_positions_put_a_visible_wall_top_on_the_skyline(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    pk = _wall_peaks()
    az, ang = sky.peak_positions(lon, lat, pk["lon"][:1], pk["lat"][:1], pk["elevation_m"][:1])
    assert abs(az[0] - 0.0) < 2.5 or abs(az[0] - 360.0) < 2.5
    assert abs(ang[0] - sky.skyline[0]) < 0.6


def test_targets_carry_distance_and_visibility(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    tg = panorama.targets(sky, lon, lat, _wall_peaks())
    assert list(tg["vis"]) == [True, False]
    assert abs(tg["distance_km"][0] - 5.0) < 0.1
    assert tg["ang"][1] < tg["ang"][0]  # the hidden peak sits below the wall top


def test_spread_keeps_labels_apart_and_centred():
    pos = panorama._spread([10.0, 10.1, 10.2], gap=1.0, lo=0.0, hi=90.0)
    assert np.all(np.diff(np.sort(pos)) >= 1.0 - 1e-9)
    assert abs(pos.mean() - 10.1) < 1e-9
    assert np.allclose(panorama._spread([5.0, 40.0], gap=1.0, lo=0.0, hi=90.0), [5.0, 40.0])


def test_richest_window_holds_the_summits_in_view(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    a0, a1 = panorama.richest_window(sky, lon, lat, _wall_peaks(), span=96.0)
    tg = panorama.targets(sky, lon, lat, _wall_peaks())
    az = float(tg["az"][0]) % 360.0
    assert a1 - a0 == 96.0
    assert a0 <= az < a1 or a0 <= az + 360.0 < a1


def test_compass_words_and_font_fallback():
    assert panorama.compass(27.0) == "NE"
    assert panorama.compass(359.0) == "N"
    assert panorama.compass(122.7) == "SE"
    assert panorama._family(("No Such Face", "DejaVu Sans")) == "DejaVu Sans"


def test_table_sheet_is_2400_wide_with_a_short_empty_strip(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    s = panorama.PanoramaStyle()
    # the wall's azimuth rounds to either side of north, so it lands in exactly one of these two strips
    out = panorama.sheet(sky, lon, lat, _wall_peaks(), tmp_path / "sheet.png", strips=((270, 360), (0, 90)), title="t", lines=["a", "b", "c", "d"], style=s)
    w, h = Image.open(out).size
    assert w == 2400
    # one strip carries both summits at full height; the other is empty and drawn short
    expected = panorama.sheet_height_in(s, [1.0, s.empty_strip_ratio], 4) * s.dpi
    assert abs(h - expected) <= 2
    assert panorama.sheet_height_in(s, [1.0], 4) > panorama.sheet_height_in(s, [1.0], 1)


def test_lines_sheet_renders_one_strip(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    out = panorama.sheet(sky, lon, lat, _wall_peaks(), tmp_path / "method.png", strips=((270, 360),), treatment="lines", title="t")
    w, h = Image.open(out).size
    assert w == 2400 and h >= 700


def test_sheet_refuses_an_unknown_treatment(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    try:
        panorama.sheet(sky, lon, lat, _wall_peaks(), tmp_path / "x.png", treatment="wash", title="t")
    except ValueError as e:
        assert "wash" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_hero_is_16_by_9_and_fills_the_compass_words(tmp_path):
    sky, lon, lat = _sky(tmp_path)
    out = panorama.hero(sky, lon, lat, _wall_peaks(), tmp_path / "hero.png", title="Wall", subtitle="from {from_dir} to {to_dir}")
    assert Image.open(out).size == (2400, 1350)
