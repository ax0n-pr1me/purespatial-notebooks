"""Figures in the site's manner: relief first, one tint for ground in view, named peaks labeled.

The relief is a composed image, not stacked layers: a multidirectional
hillshade (four lights, weighted) darkened by slope, on a light ground; where
the observer can see the ground, the tint is multiplied over the shade so the
surface stays legible inside the colour. Contours are optional and drawn on
top. `relief_map` reads the DEM at native resolution inside a window, so a
1 m lidar surface arrives at the figure as 1 m pixels.

Every visual choice is a field on `Style`. A post overrides them in its
params.py and re-runs `make run`; nothing here needs editing for a taste change.
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
import rasterio.windows
from matplotlib.colors import LightSource, to_rgb
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
    """Colour of ground in view. Multiplied over the relief, so it reads darker on shaded slopes."""
    tint_alpha: float = 0.84
    """How much of the tinted relief replaces the grey relief where ground is in view."""
    tint_feather_px: float = 0.8
    """Gaussian softening of the in-view edge, in drawn pixels; 0 keeps the raster staircase."""
    ground_warmth: float = 0.04
    """Warm cast on the grey relief (0 neutral); paper maps are not concrete."""
    ground_low: float = 0.20
    """Grey level of the darkest shaded slope (0 black, 1 white)."""
    ground_high: float = 0.985
    """Grey level of the brightest lit slope."""
    lights: tuple[tuple[float, float], ...] = ((315.0, 0.55), (270.0, 0.20), (360.0, 0.15), (225.0, 0.10))
    """Hillshade lights as (azimuth, weight); one entry gives a classic single-light shade."""
    altitude: float = 45.0
    vertical_exaggeration: float = 1.6
    slope_shade: float = 0.5
    """How much steep ground darkens on top of the hillshade (0 none, 1 strong)."""
    contrast: tuple[float, float] | None = (1.0, 99.0)
    """Percentiles of the shade stretched to the full tonal range; None keeps the raw hillshade."""
    contours_m: float | None = None
    """Contour interval in metres; None draws none."""
    index_every: int = 5
    """Every nth contour is an index line, drawn heavier and labeled when `contour_labels` is set."""
    contour_labels: bool = False
    contour_alpha: float = 0.55
    label_top: int = 20
    label_size: float = 8.5
    label_halo: float = 2.8
    marker_size: float = 36.0
    observer_size: float = 13.0
    legend: bool = True
    scale_bar: bool = True
    dpi: int = 250
    size_in: float = 11.0
    hero_dpi: int = 150
    hero_label_top: int = 12
    max_raster_px: int = 3000
    """Long side of the rasters as drawn; larger keeps more detail and costs time."""
    dark: bool = False
    """Night-map look: dark ground, luminous tint, light marks."""
    sightlines: bool = False
    """A line from the observer to every peak rated visible."""

    @property
    def ink(self) -> str:
        return "#F2F2F0" if self.dark else INK

    @property
    def paper(self) -> str:
        return "#141516" if self.dark else PAPER

    @property
    def tint_color(self) -> str:
        return "#5FD07C" if self.dark and self.tint == "#3F9457" else self.tint


DEFAULT = Style()


# ---------------------------------------------------------------- raster reading


def _bounds_window(ds, bounds):
    return rasterio.windows.from_bounds(*bounds, transform=ds.transform)


def _read_dem(path: str | Path, bounds=None, max_px: int = 3000):
    """The DEM (or a window of it) downsampled so its long side is at most max_px; nodata as NaN."""
    with rasterio.open(path) as ds:
        win = _bounds_window(ds, bounds) if bounds else rasterio.windows.Window(0, 0, ds.width, ds.height)
        w, h = round(win.width), round(win.height)
        scale = max(1.0, max(w, h) / max_px)
        shape = (max(1, round(h / scale)), max(1, round(w / scale)))
        arr = ds.read(1, window=win, out_shape=shape, resampling=Resampling.average, boundless=True, fill_value=ds.nodata if ds.nodata is not None else np.nan).astype("float32")
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        tr = rasterio.windows.transform(win, ds.transform)
        res = abs(tr.a) * (w / shape[1])
        b = rasterio.windows.bounds(win, ds.transform)
        return arr, b, ds.crs, res


def _read_mask_on(path: str | Path, bounds, shape):
    """The viewshed as a boolean on another raster's grid (same CRS): True where the ground is in view."""
    with rasterio.open(path) as ds:
        win = _bounds_window(ds, bounds)
        arr = ds.read(1, window=win, out_shape=shape, resampling=Resampling.nearest, boundless=True, fill_value=0)
    return arr >= 128


# ---------------------------------------------------------------- shading and colour


def _hillshade(dem: np.ndarray, res: float, style: Style) -> np.ndarray:
    """Weighted multidirectional hillshade in 0..1, darkened by slope."""
    filled = np.nan_to_num(dem, nan=float(np.nanmin(dem)) if np.isfinite(dem).any() else 0.0)
    shade = np.zeros_like(filled, dtype="float64")
    total = sum(w for _, w in style.lights)
    for az, w in style.lights:
        shade += (w / total) * LightSource(azdeg=az, altdeg=style.altitude).hillshade(filled, vert_exag=style.vertical_exaggeration, dx=res, dy=res)
    if style.contrast is not None:
        valid = shade[np.isfinite(dem)]
        if valid.size:
            lo, hi = np.percentile(valid, style.contrast)
            if hi > lo:
                shade = (shade - lo) / (hi - lo)
    if style.slope_shade > 0:
        gy, gx = np.gradient(filled, res)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        shade = shade * (1.0 - style.slope_shade * np.clip(slope / 75.0, 0.0, 1.0))
    return np.clip(shade, 0.0, 1.0)


def _compose(dem: np.ndarray, shade: np.ndarray, visible: np.ndarray | None, style: Style) -> np.ndarray:
    """RGB image: grey relief everywhere, tint multiplied over the relief where the ground is in view."""
    if style.dark:
        grey = 0.06 + 0.40 * shade
        tint_low, tint_high = 0.25, 1.15
        warm = np.array([1.0, 1.0, 1.0])
    else:
        grey = style.ground_low + (style.ground_high - style.ground_low) * shade
        tint_low, tint_high = 0.12, 1.12
        warm = np.array([1.0, 1.0 - 0.35 * style.ground_warmth, 1.0 - style.ground_warmth])
    rgb = np.clip(grey[..., None] * warm[None, None, :], 0.0, 1.0)
    if visible is not None and visible.any():
        from scipy.ndimage import gaussian_filter

        tint = np.asarray(to_rgb(style.tint_color))
        relief = tint_low + (tint_high - tint_low) * shade
        tinted = np.clip(relief[..., None] * tint[None, None, :], 0.0, 1.0)
        a = style.tint_alpha if not style.dark else min(style.tint_alpha, 0.75)
        mask = visible.astype("float32")
        if style.tint_feather_px > 0:
            mask = np.clip(gaussian_filter(mask, style.tint_feather_px), 0.0, 1.0)
        w = (a * mask)[..., None]
        rgb = (1 - w) * rgb + w * tinted
    paper = np.asarray(to_rgb(style.paper))
    rgb = np.where(np.isfinite(dem)[..., None], rgb, paper[None, None, :])
    return np.clip(rgb, 0.0, 1.0)


def _contours(ax, dem: np.ndarray, bounds, style: Style):
    if not style.contours_m:
        return
    finite = dem[np.isfinite(dem)]
    if finite.size == 0:
        return
    lo = np.floor(finite.min() / style.contours_m) * style.contours_m
    hi = np.ceil(finite.max() / style.contours_m) * style.contours_m
    levels = np.arange(lo, hi + style.contours_m, style.contours_m)
    if len(levels) < 2:
        return
    h, w = dem.shape
    x = np.linspace(bounds[0], bounds[2], w)
    y = np.linspace(bounds[3], bounds[1], h)
    index = levels[::style.index_every] if style.index_every > 1 else levels
    minor = np.setdiff1d(levels, index)
    color = style.ink
    if len(minor):
        ax.contour(x, y, dem, levels=minor, colors=[color], linewidths=0.28, alpha=style.contour_alpha * 0.75, zorder=3)
    cs = ax.contour(x, y, dem, levels=index, colors=[color], linewidths=0.6, alpha=style.contour_alpha, zorder=3)
    if style.contour_labels:
        ax.clabel(cs, fmt="%.0f", fontsize=6, colors=[color], inline=True, inline_spacing=4)


# ---------------------------------------------------------------- marks


def _observer_mark(ax, xy, style: Style):
    ax.plot(xy[0], xy[1], marker="^", linestyle="none", color=style.ink, markersize=style.observer_size, markeredgecolor=style.paper, markeredgewidth=1.4, zorder=6)


def _peaks(ax, fig, t, observer_xy, peaks, style: Style, label_top: int):
    """Markers for every peak; labels for the first `label_top` that fit without overlapping anything placed."""
    if peaks is None or len(peaks) == 0:
        return 0
    px, py = t.transform(peaks["lon"].to_numpy(dtype=float), peaks["lat"].to_numpy(dtype=float))
    px, py = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
    vis = (peaks["predicted"].astype(str).str.lower() == "visible").to_numpy()
    if style.sightlines and vis.any():
        for x, y in zip(px[vis], py[vis]):
            ax.plot([observer_xy[0], x], [observer_xy[1], y], color=style.tint_color, lw=0.9, alpha=0.85, zorder=4)
    ax.scatter(px[vis], py[vis], s=style.marker_size, c=style.tint_color, edgecolors=style.ink, linewidths=0.8, zorder=5)
    ax.scatter(px[~vis], py[~vis], s=style.marker_size, facecolors=style.paper, edgecolors=style.ink, linewidths=1.0, zorder=5)
    return _place_labels(ax, fig, px, py, [str(n) for n in peaks["name"]], style, label_top)


def _place_labels(ax, fig, xs, ys, names, style: Style, max_labels: int) -> int:
    """Greedy placement: try six offsets per label; keep the first that overlaps no marker, label, or edge."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axbb = ax.get_window_extent(renderer)
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    pad = style.marker_size**0.5 * 0.9
    markers = [Bbox.from_bounds(x - pad, y - pad, 2 * pad, 2 * pad) for x, y in pts]
    placed: list[Bbox] = []
    offsets = [(7, 5, "left"), (7, -12, "left"), (-7, 5, "right"), (-7, -12, "right"), (0, 10, "center"), (0, -15, "center")]
    halo = [pe.withStroke(linewidth=style.label_halo, foreground=style.paper)]
    n = 0
    for i in range(len(xs)):
        if n >= max_labels:
            break
        for dx, dy, ha in offsets:
            txt = ax.annotate(names[i], (xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points", fontsize=style.label_size, color=style.ink, ha=ha, va="center", path_effects=halo, zorder=7)
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
    handles = [Line2D([], [], marker="^", linestyle="none", color=style.ink, markersize=9, markeredgecolor=style.paper, label="Observer")]
    handles.append(Line2D([], [], marker="s", linestyle="none", color=style.tint_color, markersize=10, label="Ground in view"))
    if has_peaks:
        handles.append(Line2D([], [], marker="o", linestyle="none", markerfacecolor=style.tint_color, markeredgecolor=style.ink, markersize=7, label="Peak rated visible"))
        handles.append(Line2D([], [], marker="o", linestyle="none", markerfacecolor=style.paper, markeredgecolor=style.ink, markersize=7, label="Peak rated hidden"))
    leg = ax.legend(handles=handles, loc="lower right", fontsize=8, frameon=True, framealpha=0.92, edgecolor="none", borderpad=0.8, facecolor=style.paper)
    for text in leg.get_texts():
        text.set_color(style.ink)


def _scale_bar(ax, bounds, km: float, style: Style):
    x0 = bounds[0] + 0.05 * (bounds[2] - bounds[0])
    y0 = bounds[1] + 0.05 * (bounds[3] - bounds[1])
    ax.plot([x0, x0 + km * 1000], [y0, y0], color=style.ink, lw=2.2, solid_capstyle="butt", zorder=8)
    ax.text(x0, y0 + 0.012 * (bounds[3] - bounds[1]), f"{km:g} km", fontsize=8.5, color=style.ink, zorder=8, path_effects=[pe.withStroke(linewidth=2.5, foreground=style.paper)])


def _scale_km(bounds) -> float:
    width = bounds[2] - bounds[0]
    return 10 if width > 40_000 else (1 if width > 4_000 else 0.5)


# ---------------------------------------------------------------- the maps


def _draw_relief(ax, dem_path, vs_path, bounds, style: Style, max_px: int):
    dem, b, crs, res = _read_dem(dem_path, bounds, max_px)
    visible = _read_mask_on(vs_path, b, dem.shape) if vs_path is not None else None
    rgb = _compose(dem, _hillshade(dem, res, style), visible, style)
    ax.imshow(rgb, extent=[b[0], b[2], b[1], b[3]], interpolation="bilinear" if max_px <= 3000 else "nearest", zorder=1)
    _contours(ax, dem, b, style)
    return b, crs


def viewshed_map(dem_path, vs_path, observer, peaks, out_png, *, title: str, style: Style | None = None, label_top: int | None = None, bounds=None) -> Path:
    """Square map of the whole DEM (or `bounds`): relief, tint, contours, observer, labeled peaks, legend, scale bar."""
    s = style or DEFAULT
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(s.size_in, s.size_in), dpi=s.dpi, facecolor=s.paper)
    b, crs = _draw_relief(ax, dem_path, vs_path, bounds, s, s.max_raster_px)
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    oxy = t.transform(observer[0], observer[1])
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_aspect("equal")
    ax.set_axis_off()
    _observer_mark(ax, oxy, s)
    _peaks(ax, fig, t, oxy, peaks, s, s.label_top if label_top is None else label_top)
    if s.scale_bar:
        _scale_bar(ax, b, _scale_km(b), s)
    if s.legend:
        _legend(ax, s, peaks is not None and len(peaks) > 0)
    ax.set_title(title, loc="left", fontsize=11, color=s.ink, pad=8)
    fig.savefig(out_png, bbox_inches="tight", pad_inches=0.1, facecolor=s.paper)
    plt.close(fig)
    return out_png


def _hero_bounds(dem_path, observer, width_m: float | None):
    """A 16:9 window in map units: the whole DEM width, or `width_m` centred on the observer."""
    with rasterio.open(dem_path) as ds:
        t = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        ox, oy = t.transform(observer[0], observer[1])
        full = ds.bounds
    if width_m is None:
        width = full.right - full.left
        cx, cy = (full.left + full.right) / 2, (full.top + full.bottom) / 2
    else:
        width, cx, cy = width_m, ox, oy
    height = width * 9 / 16
    return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def hero_map(dem_path, vs_path, observer, peaks, out_png, *, style: Style | None = None, label_top: int | None = None, width_m: float | None = None, max_px: int | None = None) -> Path:
    """The map framed 16:9 for the post hero (2400 by 1350 px at the default dpi).

    `width_m` frames the window around the observer at that width, read at native resolution up to
    `max_px` pixels wide; None frames the whole DEM.
    """
    s = style or DEFAULT
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    b = _hero_bounds(dem_path, observer, width_m)
    fig, ax = plt.subplots(figsize=(16, 9), dpi=s.hero_dpi, facecolor=s.paper)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    b, crs = _draw_relief(ax, dem_path, vs_path, b, s, max_px or s.max_raster_px)
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    oxy = t.transform(observer[0], observer[1])
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_aspect("equal")
    ax.set_axis_off()
    _observer_mark(ax, oxy, s)
    _peaks(ax, fig, t, oxy, peaks, s, s.hero_label_top if label_top is None else label_top)
    fig.savefig(out_png, facecolor=s.paper)
    plt.close(fig)
    return out_png
