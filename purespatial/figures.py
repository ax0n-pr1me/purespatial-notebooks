"""Figures in the site's manner: a light grey hillshade, the viewshed as one tint, named peaks labeled.

Every map is a PNG at least 2000 px on the long side so the site can serve it
as WebP at its four widths. `hero_map` frames the same map at 16:9 for the
post hero (the site refuses heroes outside 1.6 to 2.0).

Every visual choice is a field on `Style`. A post overrides them in its
params.py (`STYLE = Style(label_top=15, tint_alpha=0.8)`) and re-runs
`make run`; nothing here needs editing for a taste change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox
from pyproj import Transformer
from rasterio.enums import Resampling

INK = "#1B1B1B"
INK_MUTED = "#6B6B6B"
ACCENT = "#2F5D3A"
PAPER = "#FFFFFF"


@dataclass
class Style:
    """The knobs. Defaults are the site's look; change them per post in params.py."""

    tint: str = "#3F9457"
    """Fill for ground the observer can see. Lighter than the site accent so it reads over grey."""
    tint_alpha: float = 0.78
    hillshade_low: float = -0.45
    """matplotlib vmin for the hillshade; more negative is a lighter, flatter relief. 0 is full contrast."""
    hillshade_high: float = 1.15
    hillshade_azimuth: float = 315.0
    hillshade_altitude: float = 45.0
    vertical_exaggeration: float = 1.0
    label_top: int = 20
    """Label at most this many peaks, in the order the caller passes them (highest first by convention)."""
    label_size: float = 8.5
    label_halo: float = 2.8
    """White stroke width behind label text."""
    marker_size: float = 36.0
    observer_size: float = 13.0
    legend: bool = True
    scale_bar: bool = True
    dpi: int = 250
    size_in: float = 11.0
    """Square map side in inches; with dpi this sets the pixel size."""
    hero_dpi: int = 150
    hero_label_top: int = 12
    max_raster_px: int = 3000
    """Rasters are downsampled to this many pixels on the long side before drawing."""


DEFAULT = Style()


def _read(path: str | Path, max_px: int, resampling: Resampling):
    """Band 1 downsampled so the long side is at most max_px, with nodata as NaN."""
    with rasterio.open(path) as ds:
        scale = max(1, int(np.ceil(max(ds.width, ds.height) / max_px)))
        shape = (max(1, ds.height // scale), max(1, ds.width // scale))
        arr = ds.read(1, out_shape=shape, resampling=resampling).astype("float32")
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        res = ds.res[0] * (ds.width / shape[1])
        return arr, ds.bounds, ds.crs, res


def _base(ax, dem_path, vs_path, observer, style: Style):
    """Hillshade, viewshed tint, observer mark. Returns the DEM bounds and the WGS84-to-map transformer."""
    dem, b, crs, res = _read(dem_path, style.max_raster_px, Resampling.average)
    vs, vb, _, _ = _read(vs_path, style.max_raster_px, Resampling.nearest)
    fill = np.nanmin(dem) if np.isfinite(dem).any() else 0.0
    ls = LightSource(azdeg=style.hillshade_azimuth, altdeg=style.hillshade_altitude)
    shade = ls.hillshade(np.nan_to_num(dem, nan=fill), vert_exag=style.vertical_exaggeration, dx=res, dy=res)
    shade = np.where(np.isfinite(dem), shade, np.nan)
    ax.imshow(
        shade, cmap="gray", vmin=style.hillshade_low, vmax=style.hillshade_high,
        extent=[b.left, b.right, b.bottom, b.top], interpolation="bilinear", zorder=1,
    )
    visible = np.where(vs >= 128, 1.0, np.nan)
    ax.imshow(
        visible, cmap=ListedColormap([style.tint]), alpha=style.tint_alpha,
        extent=[vb.left, vb.right, vb.bottom, vb.top], interpolation="nearest", zorder=2,
    )
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    ox, oy = t.transform(observer[0], observer[1])
    ax.plot(
        ox, oy, marker="^", linestyle="none", color=INK, markersize=style.observer_size,
        markeredgecolor="white", markeredgewidth=1.4, zorder=6,
    )
    return b, t


def _peaks(ax, fig, t, peaks, style: Style, label_top: int):
    """Markers for every peak; labels for the first `label_top` that fit without overlapping anything placed."""
    if peaks is None or len(peaks) == 0:
        return 0
    px, py = t.transform(peaks["lon"].to_numpy(dtype=float), peaks["lat"].to_numpy(dtype=float))
    px, py = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
    vis = (peaks["predicted"].astype(str).str.lower() == "visible").to_numpy()
    ax.scatter(px[vis], py[vis], s=style.marker_size, c=style.tint, edgecolors=INK, linewidths=0.8, zorder=5)
    ax.scatter(px[~vis], py[~vis], s=style.marker_size, facecolors="white", edgecolors=INK, linewidths=1.0, zorder=5)
    return _place_labels(ax, fig, px, py, [str(n) for n in peaks["name"]], style, label_top)


def _place_labels(ax, fig, xs, ys, names, style: Style, max_labels: int) -> int:
    """Greedy placement: try six offsets per label; keep the first that overlaps no marker, label, or edge."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axbb = ax.get_window_extent(renderer)
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    pad = style.marker_size ** 0.5 * 0.9
    markers = [Bbox.from_bounds(x - pad, y - pad, 2 * pad, 2 * pad) for x, y in pts]
    placed: list[Bbox] = []
    offsets = [(7, 5, "left"), (7, -12, "left"), (-7, 5, "right"), (-7, -12, "right"), (0, 10, "center"), (0, -15, "center")]
    halo = [pe.withStroke(linewidth=style.label_halo, foreground="white")]
    n = 0
    for i in range(len(xs)):
        if n >= max_labels:
            break
        for dx, dy, ha in offsets:
            txt = ax.annotate(
                names[i], (xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                fontsize=style.label_size, color=INK, ha=ha, va="center", path_effects=halo, zorder=7,
            )
            bb = txt.get_window_extent(renderer).expanded(1.08, 1.25)
            inside = axbb.contains(bb.x0, bb.y0) and axbb.contains(bb.x1, bb.y1)
            clash = any(bb.overlaps(p) for p in placed) or any(bb.overlaps(m) for j, m in enumerate(markers) if j != i)
            if inside and not clash:
                placed.append(bb)
                n += 1
                break
            txt.remove()
    return n


def _legend(ax, style: Style, has_peaks: bool):
    handles = [Line2D([], [], marker="^", linestyle="none", color=INK, markersize=9, markeredgecolor="white", label="Observer")]
    handles.append(Line2D([], [], marker="s", linestyle="none", color=style.tint, alpha=style.tint_alpha, markersize=10, label="Ground in view"))
    if has_peaks:
        handles.append(Line2D([], [], marker="o", linestyle="none", markerfacecolor=style.tint, markeredgecolor=INK, markersize=7, label="Peak rated visible"))
        handles.append(Line2D([], [], marker="o", linestyle="none", markerfacecolor="white", markeredgecolor=INK, markersize=7, label="Peak rated hidden"))
    ax.legend(handles=handles, loc="lower right", fontsize=8, frameon=True, framealpha=0.92, edgecolor="none", borderpad=0.8)


def _scale_bar(ax, bounds, km: float):
    x0 = bounds.left + 0.05 * (bounds.right - bounds.left)
    y0 = bounds.bottom + 0.05 * (bounds.top - bounds.bottom)
    ax.plot([x0, x0 + km * 1000], [y0, y0], color=INK, lw=2.2, solid_capstyle="butt", zorder=8)
    ax.text(
        x0, y0 + 0.012 * (bounds.top - bounds.bottom), f"{km:g} km", fontsize=8.5, color=INK, zorder=8,
        path_effects=[pe.withStroke(linewidth=2.5, foreground="white")],
    )


def viewshed_map(dem_path, vs_path, observer, peaks, out_png, *, title: str, style: Style | None = None, label_top: int | None = None) -> Path:
    """Square map: hillshade, viewshed tint, observer, peaks with de-cluttered labels, legend, scale bar."""
    s = style or DEFAULT
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(s.size_in, s.size_in), dpi=s.dpi)
    b, t = _base(ax, dem_path, vs_path, observer, s)
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(b.bottom, b.top)
    ax.set_aspect("equal")
    ax.set_axis_off()
    _peaks(ax, fig, t, peaks, s, s.label_top if label_top is None else label_top)
    if s.scale_bar:
        _scale_bar(ax, b, 10 if (b.right - b.left) > 40_000 else 1)
    if s.legend:
        _legend(ax, s, peaks is not None and len(peaks) > 0)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=8)
    fig.savefig(out_png, bbox_inches="tight", pad_inches=0.1, facecolor=PAPER)
    plt.close(fig)
    return out_png


def hero_map(dem_path, vs_path, observer, peaks, out_png, *, style: Style | None = None, label_top: int | None = None) -> Path:
    """The same map framed 16:9 around the observer for the post hero (2400 by 1350 px at the default dpi)."""
    s = style or DEFAULT
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(16, 9), dpi=s.hero_dpi)
    b, t = _base(ax, dem_path, vs_path, observer, s)
    width = b.right - b.left
    height = width * 9 / 16
    cy = (b.top + b.bottom) / 2
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(cy - height / 2, cy + height / 2)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    _peaks(ax, fig, t, peaks, s, s.hero_label_top if label_top is None else label_top)
    fig.savefig(out_png, facecolor=PAPER)
    plt.close(fig)
    return out_png
