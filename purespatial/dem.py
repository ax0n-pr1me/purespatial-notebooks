"""3DEP digital elevation models around a point, written as projected GeoTIFFs.

Every fetch lands in the post's data/ folder (gitignored) and is cached by
file name, so a notebook re-runs without re-downloading. Source: the USGS 3D
Elevation Program through py3dep, which reads the public 3DEP image service
and returns the best product available at the requested resolution: 1 m where
a lidar project covers the area, otherwise the 1/3 arc-second seamless DEM.
Output is float32 in the local UTM zone with -9999 as nodata, which is what
gdal_viewshed expects.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import rasterio.windows
import rioxarray  # noqa: F401  (registers the .rio accessor on xarray objects)
from pyproj import CRS, Transformer
from rasterio.enums import Resampling

NODATA = -9999.0


def utm_crs_for(lon: float, lat: float) -> CRS:
    """The WGS84 UTM zone containing a point (EPSG:326xx north, 327xx south)."""
    zone = math.floor((lon + 180.0) / 6.0) + 1
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def bbox_around(lon: float, lat: float, radius_m: float) -> tuple[float, float, float, float]:
    """A WGS84 (west, south, east, north) box that contains a circle of radius_m around the point."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fetch_dem(
    lon: float,
    lat: float,
    radius_m: float,
    resolution: float,
    out: str | Path,
    crs: CRS | None = None,
) -> Path:
    """Fetch a 3DEP DEM covering radius_m around the point and write it projected. Cached by `out`."""
    out = Path(out)
    if out.exists():
        return out
    # HyRiver would otherwise keep an HTTP cache (hundreds of MB of SQLite) in the working folder;
    # the GeoTIFF written below is the cache this project keeps.
    os.environ.setdefault("HYRIVER_CACHE_DISABLE", "true")
    import py3dep  # imported here so the geometry helpers and the tests need no network stack

    out.parent.mkdir(parents=True, exist_ok=True)
    crs = crs or utm_crs_for(lon, lat)
    bbox = bbox_around(lon, lat, radius_m * 1.05)
    dem = py3dep.get_dem(bbox, resolution=resolution, crs="EPSG:4326").astype("float32")
    dem = dem.where(np.isfinite(dem), NODATA)
    dem = dem.rio.write_nodata(NODATA)
    dem = dem.rio.reproject(
        crs.to_wkt(), resolution=float(resolution), resampling=Resampling.bilinear, nodata=NODATA
    )
    tmp = out.with_name(out.stem + ".part.tif")
    dem.rio.to_raster(tmp, compress="deflate", tiled=True, dtype="float32")
    tmp.replace(out)
    return out


def sample(path: str | Path, lons, lats) -> np.ndarray:
    """Raster band-1 values at WGS84 points; NaN where a point is off the raster or on nodata."""
    lons = np.atleast_1d(np.asarray(lons, dtype=float))
    lats = np.atleast_1d(np.asarray(lats, dtype=float))
    vals = np.full(lons.shape, np.nan)
    with rasterio.open(path) as ds:
        t = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        xs, ys = t.transform(lons, lats)
        b = ds.bounds
        inside = (xs >= b.left) & (xs <= b.right) & (ys >= b.bottom) & (ys <= b.top)
        if inside.any():
            pts = list(zip(np.asarray(xs)[inside], np.asarray(ys)[inside]))
            got = np.array([v[0] for v in ds.sample(pts)], dtype=float)
            if ds.nodata is not None:
                got[got == ds.nodata] = np.nan
            vals[inside] = got
    return vals


def info(path: str | Path) -> dict:
    """Shape, resolution, CRS, and bounds of a raster, for the notebook's method record."""
    with rasterio.open(path) as ds:
        return {
            "file": Path(path).name,
            "width": ds.width,
            "height": ds.height,
            "resolution_m": float(ds.res[0]),
            "crs": ds.crs.to_string(),
            "bounds": [float(v) for v in ds.bounds],
        }


def highest_point(path: str | Path, lon: float, lat: float, radius_m: float) -> tuple[float, float, float]:
    """WGS84 coordinates and elevation of the highest cell within radius_m of a point.

    Gazetteer coordinates for a summit often sit tens of metres off the crest;
    a viewshed from that cell is hidden by the summit itself. Snap first.
    """
    with rasterio.open(path) as ds:
        to_map = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        to_wgs = Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
        x, y = to_map.transform(lon, lat)
        res = ds.res[0]
        r = int(math.ceil(radius_m / res))
        row, col = ds.index(x, y)
        r0, c0 = max(row - r, 0), max(col - r, 0)
        r1, c1 = min(row + r + 1, ds.height), min(col + r + 1, ds.width)
        win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        arr = ds.read(1, window=win).astype("float64")
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        rows, cols = np.mgrid[r0:r1, c0:c1]
        cx, cy = rasterio.transform.xy(ds.transform, rows.ravel(), cols.ravel())
        dist = np.hypot(np.asarray(cx, dtype=float) - x, np.asarray(cy, dtype=float) - y).reshape(arr.shape)
        arr[dist > radius_m] = np.nan
        if not np.isfinite(arr).any():
            raise ValueError(f"no elevation within {radius_m} m of ({lon}, {lat}) in {Path(path).name}")
        i = np.nanargmax(arr)
        rr, cc = np.unravel_index(i, arr.shape)
        px, py = ds.xy(r0 + rr, c0 + cc)
        plon, plat = to_wgs.transform(px, py)
    return float(plon), float(plat), float(arr[rr, cc])
