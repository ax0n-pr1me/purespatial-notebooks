"""gdal_viewshed around an observer given in WGS84.

The output is a binary raster on the DEM's grid, cropped to the maximum
distance: 255 where the ground is visible from the observer, 0 where it is
not. The observer stands observer_height metres above the DEM at its cell;
Earth curvature and standard atmospheric refraction are applied through
GDAL's curvature coefficient (0.85714, the usual 1 minus 1/7).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import rasterio
from pyproj import Transformer

CURVATURE = 0.85714


def gdal_viewshed_path() -> str:
    exe = shutil.which("gdal_viewshed")
    if not exe:
        raise RuntimeError("gdal_viewshed is not on PATH; install GDAL (macOS: brew install gdal)")
    return exe


def to_raster_xy(dem: str | Path, lon: float, lat: float) -> tuple[float, float]:
    """The observer's coordinates in the DEM's CRS; raises if the point is off the raster."""
    with rasterio.open(dem) as ds:
        t = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        x, y = t.transform(lon, lat)
        b = ds.bounds
        if not (b.left <= x <= b.right and b.bottom <= y <= b.top):
            raise ValueError(f"observer ({lon}, {lat}) falls outside {Path(dem).name}")
    return float(x), float(y)


def run_viewshed(
    dem: str | Path,
    lon: float,
    lat: float,
    out: str | Path,
    *,
    observer_height: float = 1.7,
    target_height: float = 0.0,
    max_distance: float | None = None,
    curvature: float = CURVATURE,
) -> Path:
    """Run gdal_viewshed; 255 visible, 0 hidden. Cached by `out`."""
    out = Path(out)
    if out.exists():
        return out
    x, y = to_raster_xy(dem, lon, lat)
    cmd = [
        gdal_viewshed_path(),
        "-b", "1",
        "-ox", f"{x:.3f}",
        "-oy", f"{y:.3f}",
        "-oz", str(observer_height),
        "-tz", str(target_height),
        "-cc", str(curvature),
        "-om", "NORMAL",
        "-vv", "255",
        "-iv", "0",
        "-ov", "0",
        "-co", "COMPRESS=DEFLATE",
        "-co", "TILED=YES",
    ]
    if max_distance:
        cmd += ["-md", f"{float(max_distance):.1f}"]
    tmp = out.with_name(out.stem + ".part.tif")
    cmd += [str(dem), str(tmp)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"gdal_viewshed failed ({proc.returncode}): {proc.stderr.strip()}")
    tmp.replace(out)
    return out


def visible_fraction(path: str | Path) -> float:
    """Share of in-range cells the observer can see."""

    with rasterio.open(path) as ds:
        arr = ds.read(1)
    return float((arr >= 128).sum() / arr.size) if arr.size else float("nan")
