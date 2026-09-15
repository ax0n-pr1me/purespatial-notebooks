"""Figures in the site's manner: a grey hillshade, the viewshed as one accent tint, named peaks labeled.

Every figure is a PNG at least 2000 px wide so the site can serve it as WebP
at its four widths. `hero_map` frames the same map at 16:9 for the post's
hero (the site refuses heroes outside 1.6 to 2.0).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, ListedColormap
from pyproj import Transformer
from rasterio.enums import Resampling

INK = "#1B1B1B"
INK_MUTED = "#6B6B6B"
ACCENT = "#2F5D3A"
PAPER = "#FFFFFF"


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


def _scale_bar(ax, bounds, km: float):
    x0 = bounds.left + 0.05 * (bounds.right - bounds.left)
    y0 = bounds.bottom + 0.05 * (bounds.top - bounds.bottom)
    ax.plot([x0, x0 + km * 1000], [y0, y0], color=INK, lw=2, solid_capstyle="butt")
    ax.text(x0, y0 + 0.012 * (bounds.top - bounds.bottom), f"{km:g} km", fontsize=8, color=INK)


def _draw(ax, dem_path, vs_path, observer, peaks, label_top: int):
    dem, b, crs, res = _read(dem_path, 3000, Resampling.average)
    vs, vb, _, _ = _read(vs_path, 3000, Resampling.nearest)
    fill = np.nanmin(dem) if np.isfinite(dem).any() else 0.0
    shade = LightSource(azdeg=315, altdeg=45).hillshade(np.nan_to_num(dem, nan=fill), vert_exag=1.0, dx=res, dy=res)
    ax.imshow(shade, cmap="gray", vmin=0.0, vmax=1.0, extent=[b.left, b.right, b.bottom, b.top], interpolation="bilinear")
    visible = np.where(vs >= 128, 1.0, np.nan)
    ax.imshow(visible, cmap=ListedColormap([ACCENT]), alpha=0.45, extent=[vb.left, vb.right, vb.bottom, vb.top], interpolation="nearest")
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    ox, oy = t.transform(observer[0], observer[1])
    ax.plot(ox, oy, marker="^", color=INK, markersize=11, markeredgecolor="white", markeredgewidth=1.2, zorder=6)
    if peaks is not None and len(peaks):
        px, py = t.transform(peaks["lon"].to_numpy(dtype=float), peaks["lat"].to_numpy(dtype=float))
        px, py = np.asarray(px), np.asarray(py)
        vis = (peaks["predicted"].astype(str).str.lower() == "visible").to_numpy()
        ax.scatter(px[vis], py[vis], s=30, c=ACCENT, edgecolors="white", linewidths=0.7, zorder=5)
        ax.scatter(px[~vis], py[~vis], s=30, facecolors="none", edgecolors=INK, linewidths=0.9, zorder=5)
        for i, (x, y, name) in enumerate(zip(px, py, peaks["name"])):
            if i >= label_top:
                break
            ax.annotate(str(name), (x, y), xytext=(4, 3), textcoords="offset points", fontsize=7, color=INK)
    return b


def viewshed_map(dem_path, vs_path, observer, peaks, out_png, *, title: str, label_top: int = 40, dpi: int = 250) -> Path:
    """Square map of the viewshed on a hillshade with the peaks the model rates, at least 2000 px."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 11), dpi=dpi)
    b = _draw(ax, dem_path, vs_path, observer, peaks, label_top)
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(b.bottom, b.top)
    ax.set_aspect("equal")
    ax.set_axis_off()
    _scale_bar(ax, b, 10 if (b.right - b.left) > 40_000 else 1)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=8)
    fig.savefig(out_png, bbox_inches="tight", pad_inches=0.1, facecolor=PAPER)
    plt.close(fig)
    return out_png


def hero_map(dem_path, vs_path, observer, peaks, out_png, *, label_top: int = 12, dpi: int = 150) -> Path:
    """The same map framed 16:9 around the observer for the post hero (2400 by 1350 px)."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(16, 9), dpi=dpi)
    b = _draw(ax, dem_path, vs_path, observer, peaks, label_top)
    width = b.right - b.left
    height = width * 9 / 16
    cy = (b.top + b.bottom) / 2
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(cy - height / 2, cy + height / 2)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(out_png, facecolor=PAPER)
    plt.close(fig)
    return out_png
