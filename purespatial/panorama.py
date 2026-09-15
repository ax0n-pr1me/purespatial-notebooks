"""The view itself: a skyline panorama computed from the DEM, ridge by ridge.

For every true azimuth a ray leaves the observer and samples the DEM out to
the far radius. Each sample has an elevation angle (with Earth curvature and
standard refraction, the same coefficient gdal_viewshed uses); the skyline is
the largest angle along the ray. Drawing distance bands far to near, each
filled from the bottom up to its own maximum angle, gives the silhouettes
that are in view, with nearer ridges occluding farther ones. Peaks are placed
at their own azimuth and angle: visible ones stand on the skyline, hidden
ones fall inside the grey of the ridge that hides them.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from pyproj import Geod, Transformer
from scipy.ndimage import map_coordinates

from .figures import INK, INK_MUTED, PAPER, Style

R_EARTH = 6_371_000.0
_GEOD = Geod(ellps="WGS84")
COMPASS = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW", 360: "N"}


@dataclass
class Skyline:
    azimuth: np.ndarray
    """True azimuth of each ray, degrees, shape (n_az,)."""
    distance: np.ndarray
    """Sample distances along a ray, metres, shape (n_d,)."""
    angle: np.ndarray
    """Elevation angle of the terrain at each sample, degrees, shape (n_az, n_d); NaN off the DEM."""
    skyline: np.ndarray
    """Largest angle along each ray, degrees, shape (n_az,)."""
    observer_elevation: float
    """DEM elevation at the observer plus the eye height, metres."""
    curvature: float

    def peak_positions(self, lon: float, lat: float, lons, lats, elevations) -> tuple[np.ndarray, np.ndarray]:
        """True azimuth and elevation angle of targets as the observer sees them (same curvature model)."""
        lons = np.atleast_1d(np.asarray(lons, dtype=float))
        lats = np.atleast_1d(np.asarray(lats, dtype=float))
        elev = np.atleast_1d(np.asarray(elevations, dtype=float))
        az, _, dist = _GEOD.inv(np.full(lons.shape, lon), np.full(lats.shape, lat), lons, lats)
        az = np.mod(az, 360.0)
        drop = self.curvature * dist**2 / (2 * R_EARTH)
        angle = np.degrees(np.arctan2(elev - self.observer_elevation - drop, dist))
        return az, angle


def compute_skyline(
    dem_path: str | Path,
    lon: float,
    lat: float,
    *,
    observer_height: float = 1.7,
    max_distance: float = 60_000.0,
    step: float | None = None,
    az_step: float = 0.05,
    curvature: float = 0.85714,
    observer_elevation: float | None = None,
) -> Skyline:
    """Cast rays in true azimuth from the observer and read the DEM along each one.

    `observer_elevation` is the ground under the observer's feet. Pass the crest
    elevation from the finest DEM you have: a coarse grid interpolates the
    summit away, and a ray that starts below the summit cell sees the summit as
    a wall.
    """
    with rasterio.open(dem_path) as ds:
        arr = ds.read(1).astype("float32")
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        to_map = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        ox, oy = to_map.transform(lon, lat)
        nx, ny = to_map.transform(lon, lat + 0.001)
        tr = ds.transform
        res = float(ds.res[0])
    # grid convergence: the grid azimuth of true north at the observer
    gamma = math.degrees(math.atan2(nx - ox, ny - oy))
    step = step or res
    col0 = (ox - tr.c) / tr.a
    row0 = (oy - tr.f) / tr.e
    ground = observer_elevation if observer_elevation is not None else float(map_coordinates(arr, [[row0], [col0]], order=1, mode="nearest")[0])
    z_obs = ground + observer_height

    az = np.arange(0.0, 360.0, az_step)
    d = np.arange(step, max_distance + step / 2, step)
    grid_az = np.radians(az + gamma)[:, None]
    xs = ox + d[None, :] * np.sin(grid_az)
    ys = oy + d[None, :] * np.cos(grid_az)
    cols = (xs - tr.c) / tr.a
    rows = (ys - tr.f) / tr.e
    z = map_coordinates(arr, [rows.ravel(), cols.ravel()], order=1, mode="constant", cval=np.nan).reshape(xs.shape)
    drop = curvature * d[None, :] ** 2 / (2 * R_EARTH)
    angle = np.degrees(np.arctan2(z - z_obs - drop, d[None, :])).astype("float32")
    finite = np.isfinite(angle)
    skyline = np.where(finite.any(axis=1), np.nanmax(np.where(finite, angle, -np.inf), axis=1), np.nan)
    return Skyline(az, d, angle, skyline.astype("float64"), z_obs, curvature)


def _depth_bands(sky: Skyline, edges_km: list[float]) -> list[tuple[float, np.ndarray]]:
    """Per distance band, the max angle along each ray, farthest band first."""
    out = []
    edges = [e * 1000.0 for e in edges_km]
    for lo, hi in itertools.pairwise(edges):
        m = (sky.distance >= lo) & (sky.distance < hi)
        band = sky.angle[:, m]
        finite = np.isfinite(band)
        prof = np.where(finite.any(axis=1), np.nanmax(np.where(finite, band, -np.inf), axis=1), np.nan)
        out.append((hi, prof))
    return list(reversed(out))


def _place_vertical_labels(ax, fig, xs, ys, names, colors, y_top, style: Style, *, size: float):
    """Labels rotated 90 degrees above their peak, pushed upward in steps until they fit."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axbb = ax.get_window_extent(renderer)
    placed = []
    lifts = [0.35, 0.9, 1.5, 2.15, 2.85]
    n = 0
    for x, y, name, color in zip(xs, ys, names, colors):
        for lift in lifts:
            y_text = y + lift
            if y_text > y_top:
                break
            txt = ax.text(
                x, y_text, name, rotation=90, ha="center", va="bottom", fontsize=size, color=color,
                path_effects=[pe.withStroke(linewidth=style.label_halo, foreground=PAPER)], zorder=9,
            )
            bb = txt.get_window_extent(renderer).expanded(1.15, 1.06)
            inside = axbb.contains(bb.x0, bb.y0) and axbb.contains(bb.x1, bb.y1)
            if inside and not any(bb.overlaps(p) for p in placed):
                ax.plot([x, x], [y, y_text - 0.05], color=color, lw=0.6, alpha=0.9, zorder=8)
                placed.append(bb)
                n += 1
                break
            txt.remove()
    return n


def render(
    sky: Skyline,
    lon: float,
    lat: float,
    peaks,
    out_png: str | Path,
    *,
    style: Style | None = None,
    title: str | None = None,
    rows: int = 2,
    figsize: tuple[float, float] = (16, 9),
    dpi: int = 150,
    band_edges_km: list[float] | None = None,
    label_top: int = 24,
) -> Path:
    """Two stacked half-turns (N to S over E, then S to N over W) at 16:9; title None for the hero."""
    s = style or Style()
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    edges = band_edges_km or [0, 1.5, 3, 6, 10, 16, 24, 34, 46, 60]
    bands = _depth_bands(sky, edges)
    greys = np.linspace(0.84, 0.30, len(bands))  # far light, near dark
    finite = np.isfinite(sky.skyline)
    y_lo = float(np.nanmin(sky.skyline[finite])) - 1.2 if finite.any() else -5.0
    y_hi = float(np.nanmax(sky.skyline[finite])) + 3.8 if finite.any() else 5.0

    if peaks is not None and len(peaks):
        p_az, p_ang = sky.peak_positions(lon, lat, peaks["lon"], peaks["lat"], peaks["elevation_m"])
        p_vis = (peaks["predicted"].astype(str).str.lower() == "visible").to_numpy()
        p_names = [str(n) for n in peaks["name"]]
    else:
        p_az = p_ang = np.array([])
        p_vis = np.array([], dtype=bool)
        p_names = []

    fig, axes = plt.subplots(rows, 1, figsize=figsize, dpi=dpi, facecolor=PAPER)
    axes = np.atleast_1d(axes)
    span = 360.0 / rows
    for k, ax in enumerate(axes):
        a0, a1 = k * span, (k + 1) * span
        sel = (sky.azimuth >= a0 - 1e-9) & (sky.azimuth <= a1 + 1e-9)
        x = sky.azimuth[sel]
        for (hi, prof), g in zip(bands, greys):
            y = prof[sel]
            ax.fill_between(x, y_lo - 5, np.where(np.isfinite(y), y, y_lo - 5), color=str(g), lw=0, zorder=2)
        ax.plot(x, sky.skyline[sel], color=INK, lw=0.5, alpha=0.55, zorder=3)
        ax.set_xlim(a0, a1)
        ax.set_ylim(y_lo, y_hi)
        ax.set_facecolor(PAPER)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_yticks([])
        ticks = [t for t in range(0, 361, 45) if a0 - 1e-9 <= t <= a1 + 1e-9]
        ax.set_xticks(ticks)
        ax.set_xticklabels([COMPASS[t] for t in ticks], fontsize=9, color=INK_MUTED)
        ax.xaxis.set_ticks_position("top")
        ax.tick_params(axis="x", length=0, pad=4)
        ax.axhline(0.0, color=INK_MUTED, lw=0.4, ls=(0, (2, 4)), alpha=0.7, zorder=4)
        if len(p_az):
            in_row = (p_az >= a0) & (p_az < a1) if k < rows - 1 else (p_az >= a0) & (p_az <= a1)
            v = in_row & p_vis
            h = in_row & ~p_vis
            ax.scatter(p_az[v], p_ang[v], s=26, c=s.tint, edgecolors=INK, linewidths=0.7, zorder=6)
            ax.scatter(p_az[h], p_ang[h], s=22, facecolors=PAPER, edgecolors=INK, linewidths=0.8, zorder=6)
            order = [i for i in np.argsort(-p_ang) if in_row[i] and p_vis[i]] + [i for i in np.argsort(-p_ang) if in_row[i] and not p_vis[i]]
            order = order[:label_top]
            _place_vertical_labels(
                ax, fig, p_az[order], p_ang[order], [p_names[i] for i in order],
                [INK if p_vis[i] else INK_MUTED for i in order], y_hi - 0.1, s, size=7.6,
            )
    if title:
        axes[0].set_title(title, loc="left", fontsize=11, color=INK, pad=18)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.95 if title else 0.965, bottom=0.01, hspace=0.16)
    fig.savefig(out_png, facecolor=PAPER)
    plt.close(fig)
    return out_png
