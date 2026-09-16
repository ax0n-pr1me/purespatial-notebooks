"""The view itself: a skyline panorama computed from the DEM, ridge by ridge, drawn as the site draws it.

For every true azimuth a ray leaves the observer and samples the DEM out to
the far radius. Each sample has an elevation angle (with Earth curvature and
standard refraction, the same coefficient gdal_viewshed uses); the skyline is
the largest angle along the ray. Drawing distance bands far to near, each
filled from the bottom up to its own maximum angle, gives the silhouettes
that are in view, with nearer ridges occluding farther ones. Peaks are placed
at their own azimuth and angle: visible ones stand on the skyline, hidden
ones fall inside the ridge that hides them.

Three treatments, chosen on the design board of 2026-09-16:

  table     the alpine orientation table: warm paper, flat tonal ridges pale at
            the far radius and umber near, each closed by a crest line. The
            Result sheets, east and west, two quarter-turns each.
  lines     stacked distance slices as fine profiles, fainter with distance,
            the skyline heavy on top: a picture of what the rays compute. The
            Method figure.
  nocturne  the hero: black ridges against a dusk glow, rim-lit crests,
            luminous marks for summits in view, the title set in the sky.

Every strip carries the same foundation: the site's type, a bearing scale with
compass points, leaders that fan from each summit to its name with elevation
and distance, a filled accent mark for a summit in view and a hollow one for a
summit behind a nearer ridge, a level line at 0 degrees, and one vertical scale
across all strips, stated in the title block.

Every visual choice is a field on `PanoramaStyle`; a post overrides it in its
params.py. Fonts: the first installed family in `serif` and `sans` is used.
Files in `purespatial/fonts/` are registered first, so an open face dropped
there (Charter is free to redistribute; IBM Plex Sans is OFL) travels with the
repository and renders the same on any machine.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib import font_manager
from matplotlib.colors import to_rgb
from matplotlib.patches import Ellipse, Rectangle
from pyproj import Geod, Transformer
from scipy.ndimage import map_coordinates

R_EARTH = 6_371_000.0
_GEOD = Geod(ellps="WGS84")
COMPASS = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW", 360: "N"}
COMPASS_WORDS = {
    "N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
    "S": "south", "SW": "southwest", "W": "west", "NW": "northwest",
}

for _font in sorted((Path(__file__).parent / "fonts").glob("*.[ot]tf")):
    font_manager.fontManager.addfont(str(_font))


def _family(candidates: tuple[str, ...]) -> str:
    """The first family in `candidates` that matplotlib can see; the last one is the fallback."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    for c in candidates:
        if c in names:
            return c
    return candidates[-1]


def compass(az: float) -> str:
    """The nearest of the eight compass points, as its letters."""
    return COMPASS[round(float(az) / 45.0) % 8 * 45]


@dataclass
class PanoramaStyle:
    """The knobs. Defaults are the site's look; change them per post in params.py."""

    serif: tuple[str, ...] = ("Charter", "Iowan Old Style", "Source Serif 4", "Georgia", "DejaVu Serif")
    """Names of summits and the title, first installed wins."""
    sans: tuple[str, ...] = ("Avenir Next", "IBM Plex Sans", "Source Sans 3", "Helvetica Neue", "DejaVu Sans")
    """Numerals, the bearing scale, and the title block's lines."""

    # sheet tokens: DESIGN.md ink and accent on a paper a hair warmer than the site's white
    paper: str = "#FAF8F4"
    ink: str = "#1A1A1A"
    muted: str = "#5A5A5A"
    hair: str = "#D6D2CA"
    accent: str = "#2F5D3A"

    # table: flat tonal ridges from the far radius to the nearest band, closed by a crest line
    far_tone: str = "#E6E1D8"
    near_tone: str = "#4B443C"
    crest: str = "#2A2521"
    band_edges_km: tuple[float, ...] = (0, 0.8, 1.6, 2.5, 3.5, 5, 7, 9.5, 12.5, 16, 20, 25, 30, 36, 43, 51, 60)

    # lines: stacked slices, each a profile that hides what lies behind it
    line_fill: str = "#F0EDE7"
    line_edges_km: tuple[float, ...] = field(default_factory=lambda: tuple(np.round(np.geomspace(0.7, 60, 41), 3)))

    # geometry of a sheet
    dpi: int = 150
    width_in: float = 16.0
    strip_in: float = 3.6
    """Height of a strip that carries labels; a strip with no named summit gets `empty_strip_ratio` of it."""
    empty_strip_ratio: float = 0.56
    title_in: float = 1.35
    gap_in: float = 0.18
    bottom_in: float = 0.3
    margin: float = 0.035
    exaggeration: float = 1.35
    """Vertical scale of the terrain relative to the bearing scale; stated in the title block."""
    scale_room: float = 1.0
    """Degrees of data space kept under the terrain for the bearing scale."""
    label_lift: float = 0.42
    """Degrees above the strip's highest ridge where every label's baseline sits."""
    name_size: float = 11.0
    sub_size: float = 7.2
    marker: float = 44.0

    # hero: nocturne at 16:9
    hero_span: float = 96.0
    """Degrees of azimuth in the hero; `richest_window` centres it on the most summits in view."""
    hero_exaggeration: float = 4.0
    hero_name_size: float = 11.5
    hero_sub_size: float = 7.6
    hero_marker: float = 56.0
    night_ground: str = "#121412"
    night_ink: str = "#ECEDE9"
    night_muted: str = "#A6A8A2"
    night_hair: str = "#2A2D2A"
    night_accent: str = "#7FB08A"
    glow: str = "#4E6052"
    sky_top: str = "#0C0E0C"
    night_far: str = "#3A443D"
    night_near: str = "#080908"
    rim: str = "#B9C7BC"
    glow_sigma: float = 2.4

    source: str = "USGS 3DEP · USGS GNIS · purespatial.com"

    @property
    def serif_family(self) -> str:
        return _family(self.serif)

    @property
    def sans_family(self) -> str:
        return _family(self.sans)


DEFAULT = PanoramaStyle()


# ---------------------------------------------------------------- the skyline


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

    def closed(self) -> tuple[np.ndarray, np.ndarray]:
        """Azimuths and skyline with the first ray repeated at 360, so a strip ending at north closes."""
        return np.append(self.azimuth, 360.0), np.append(self.skyline, self.skyline[0])


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


def _profiles(sky: Skyline, edges_km) -> list[np.ndarray]:
    """Per distance band, the max angle along each ray, FAR band first, each closed at 360."""
    edges = np.asarray(edges_km, dtype=float) * 1000.0
    out = []
    for lo, hi in itertools.pairwise(edges):
        m = (sky.distance >= lo) & (sky.distance < hi)
        band = sky.angle[:, m]
        if band.shape[1] == 0:  # a band beyond the DEM or the far radius: nothing to draw
            prof = np.full(sky.azimuth.shape, np.nan)
        else:
            finite = np.isfinite(band)
            prof = np.where(finite.any(axis=1), np.nanmax(np.where(finite, band, -np.inf), axis=1), np.nan)
        out.append(np.append(prof, prof[0]))
    return out[::-1]


def targets(sky: Skyline, lon: float, lat: float, peaks) -> pd.DataFrame:
    """The rated summits as the observer sees them: name, az, ang, vis, elevation_m, distance_km."""
    if peaks is None or len(peaks) == 0:
        return pd.DataFrame(columns=["name", "az", "ang", "vis", "elevation_m", "distance_km"])
    lons = peaks["lon"].to_numpy(dtype=float)
    lats = peaks["lat"].to_numpy(dtype=float)
    az, ang = sky.peak_positions(lon, lat, lons, lats, peaks["elevation_m"])
    _, _, dist = _GEOD.inv(np.full(lons.shape, lon), np.full(lats.shape, lat), lons, lats)
    return pd.DataFrame({
        "name": [str(n) for n in peaks["name"]],
        "az": az,
        "ang": ang,
        "vis": (peaks["predicted"].astype(str).str.lower() == "visible").to_numpy(),
        "elevation_m": peaks["elevation_m"].to_numpy(dtype=float),
        "distance_km": np.asarray(dist, dtype=float) / 1000.0,
    })


def richest_window(sky: Skyline, lon: float, lat: float, peaks, span: float = 96.0) -> tuple[float, float]:
    """The `span`-degree window (within 0 to 360) holding the most summits in view, centred on them."""
    tg = targets(sky, lon, lat, peaks)
    vis = np.sort(tg.loc[tg["vis"], "az"].to_numpy(dtype=float))
    if len(vis) == 0:
        return 0.0, float(span)
    best_n, best_a0 = -1, 0.0
    for a0 in np.arange(0.0, 360.0 - span + 1e-9, 1.0):
        n = int(np.sum((vis >= a0) & (vis < a0 + span)))
        if n > best_n:
            best_n, best_a0 = n, a0
    inside = vis[(vis >= best_a0) & (vis < best_a0 + span)]
    centre = (inside.min() + inside.max()) / 2
    a0 = float(np.clip(round(centre - span / 2), 0.0, 360.0 - span))
    return a0, a0 + span


# ---------------------------------------------------------------- shared drawing


def _mix(c0: str, c1: str, t: float) -> tuple[float, float, float]:
    a, b = np.asarray(to_rgb(c0)), np.asarray(to_rgb(c1))
    return tuple(np.clip(a + (b - a) * t, 0.0, 1.0))


def _spread(x, gap: float, lo: float, hi: float) -> np.ndarray:
    """1-D placement: every label at least `gap` apart, each cluster centred on its members' mean."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x)
    xs = x[order]
    clusters = [[i] for i in range(len(xs))]

    def bounds(c):
        w = (len(c) - 1) * gap
        centre = xs[c].mean()
        return centre - w / 2, centre + w / 2

    merged = True
    while merged:
        merged = False
        new, i = [], 0
        while i < len(clusters):
            c = clusters[i]
            if i + 1 < len(clusters):
                _, r1 = bounds(c)
                l2, _ = bounds(clusters[i + 1])
                if r1 + gap > l2:
                    new.append(c + clusters[i + 1])
                    i += 2
                    merged = True
                    continue
            new.append(c)
            i += 1
        clusters = new
    pos = np.empty_like(xs)
    for c in clusters:
        lo_c, hi_c = bounds(c)
        shift = max(lo - lo_c, 0.0) - max(hi_c - hi, 0.0)
        for k, idx in enumerate(c):
            pos[idx] = lo_c + shift + k * gap
    out = np.empty_like(pos)
    out[order] = pos
    return out


def _px_per_deg(ax, fig) -> tuple[float, float]:
    pos = ax.get_position()
    w_px = pos.width * fig.get_figwidth() * fig.dpi
    h_px = pos.height * fig.get_figheight() * fig.dpi
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    return w_px / (x1 - x0), h_px / (y1 - y0)


class _Zone:
    """A clip rectangle for everything terrain: nothing drawn for the ridges enters the scale zone below y0."""

    def __init__(self, ax, y0: float):
        x0, x1 = ax.get_xlim()
        _, y1 = ax.get_ylim()
        self.rect = Rectangle((x0, y0), x1 - x0, y1 - y0, transform=ax.transData)

    def __call__(self, artist):
        artist.set_clip_path(self.rect)
        return artist


@dataclass(frozen=True)
class _Marks:
    """Colours for one strip's labels and marks."""

    name: str
    hidden: str
    sub: str
    leader: str
    vis_face: str
    vis_edge: str
    hid_face: str
    hid_edge: str


def _labels(ax, fig, tg: pd.DataFrame, a0: float, a1: float, yb: float, s: PanoramaStyle, m: _Marks, *, name_size: float, sub_size: float, marker: float) -> int:
    """Fanning leaders from each summit to a common baseline, the name set upright, then elevation and distance.

    Returns how many elevation lines were dropped for lack of room above the strip.
    """
    if len(tg) == 0:
        return 0
    renderer = fig.canvas.get_renderer()
    pxx, _ = _px_per_deg(ax, fig)
    gap = name_size * fig.dpi / 72 * 1.36 / pxx
    xl = _spread(tg["az"].to_numpy(), gap, a0 + gap * 0.7, a1 - gap * 0.7)
    inv = ax.transData.inverted()
    y_top = ax.get_ylim()[1]
    serif, sans = s.serif_family, s.sans_family
    dropped = 0
    for (_, r), x in zip(tg.iterrows(), xl):
        ax.plot([r["az"], x], [r["ang"], yb], color=m.leader, lw=0.55, alpha=0.8 if r["vis"] else 0.5, zorder=8, solid_capstyle="round")
        t = ax.text(x, yb + 0.14, r["name"], rotation=90, ha="center", va="bottom", fontsize=name_size, fontfamily=serif, color=m.name if r["vis"] else m.hidden, zorder=9)
        top = inv.transform((0, t.get_window_extent(renderer).y1))[1]
        sub = ax.text(x, top + 0.2, f"{r['elevation_m']:,.0f} m · {r['distance_km']:.0f} km", rotation=90, ha="center", va="bottom", fontsize=sub_size, fontfamily=sans, color=m.sub, zorder=9)
        if inv.transform((0, sub.get_window_extent(renderer).y1))[1] > y_top:
            sub.remove()
            dropped += 1
    v, h = tg[tg["vis"]], tg[~tg["vis"]]
    ax.scatter(v["az"], v["ang"], s=marker, c=[m.vis_face], edgecolors=m.vis_edge, linewidths=1.1, zorder=10)
    ax.scatter(h["az"], h["ang"], s=marker * 0.8, facecolors=m.hid_face, edgecolors=m.hid_edge, linewidths=0.9, zorder=10)
    return dropped


def _scale(ax, fig, a0: float, a1: float, y_base: float, s: PanoramaStyle, *, ink: str, muted: str, hair: str, num_size: float, comp_size: float):
    """Bearing scale: hairline baseline, ticks every 5 degrees, numerals every 15, compass points at 45."""
    _, pxy = _px_per_deg(ax, fig)
    sans = s.sans_family
    ax.plot([a0, a1], [y_base, y_base], color=hair, lw=0.8, zorder=7, solid_capstyle="butt")
    for a in np.arange(np.ceil(a0 / 5.0) * 5.0, a1 + 1e-9, 5.0):
        deg = round(a)
        big = deg % 15 == 0
        ax.plot([a, a], [y_base, y_base - (7 if big else 3.5) / pxy], color=muted, lw=0.6, zorder=7)
        if not big:
            continue
        if deg % 45 == 0:
            ax.text(a, y_base - 11 / pxy, COMPASS[deg % 360], ha="center", va="top", fontsize=comp_size, fontfamily=sans, fontweight="semibold", color=ink, zorder=7)
        else:
            ax.text(a, y_base - 11 / pxy, f"{deg % 360}°", ha="center", va="top", fontsize=num_size, fontfamily=sans, color=muted, zorder=7)


def _level_line(ax, a0: float, a1: float, sky_strip: np.ndarray, s: PanoramaStyle, *, hair: str, muted: str):
    ax.plot([a0, a1], [0, 0], color=hair, lw=0.7, zorder=1)
    tail = sky_strip[-200:]
    if np.isfinite(tail).any() and np.nanmax(tail) < -0.15:
        ax.text(a1 - 0.4, 0.08, "0°, level", ha="right", va="bottom", fontsize=6.8, fontfamily=s.sans_family, color=muted, zorder=1)


def _title_height_in(s: PanoramaStyle, n_lines: int) -> float:
    """The title block's height: at least `title_in`, more when its lines would otherwise reach the first strip."""
    return max(s.title_in, 0.45 + 0.41 + 0.195 * n_lines + 0.14)


def sheet_height_in(s: PanoramaStyle, ratios, n_lines: int) -> float:
    """Height of a sheet in inches: title block, the strips at their ratios, the gaps, the bottom margin."""
    return _title_height_in(s, n_lines) + s.strip_in * sum(ratios) + s.gap_in * (len(ratios) - 1) + s.bottom_in


def _title_block(fig, s: PanoramaStyle, *, title: str, lines, ink: str, muted: str, left: float, right: float):
    h_in = fig.get_figheight()
    fig.text(left, 1 - 0.45 / h_in, title, fontsize=24, fontfamily=s.serif_family, color=ink, va="top", ha="left")
    for i, line in enumerate(lines):
        fig.text(left, 1 - (0.45 + 0.41 + 0.195 * i) / h_in, line, fontsize=9.6, fontfamily=s.sans_family, color=muted, va="top", ha="left")
    fig.text(right, 1 - 0.45 / h_in, s.source, fontsize=7.6, fontfamily=s.sans_family, color=muted, va="top", ha="right")


# ---------------------------------------------------------------- terrain treatments


def _terrain_table(ax, X, bands, y0: float, s: PanoramaStyle):
    """Flat tonal silhouettes, far pale to near dark, each ridge closed by a crest line."""
    clip = _Zone(ax, y0)
    n = len(bands)
    for k, prof in enumerate(bands):  # far to near
        t = k / max(n - 1, 1)
        prof = np.nan_to_num(prof, nan=y0 - 1)
        clip(ax.fill_between(X, y0 - 1, prof, color=_mix(s.far_tone, s.near_tone, t**1.25), lw=0, zorder=2 + 2 * k))
        clip(ax.plot(X, prof, color=s.crest, lw=0.5 + 0.45 * t, alpha=0.55 + 0.45 * t, zorder=3 + 2 * k)[0])


def _terrain_lines(ax, X, slices, skyline, y0: float, s: PanoramaStyle):
    """Stacked profiles: every slice hides what lies behind it, then draws its own line; the skyline closes it."""
    clip = _Zone(ax, y0)
    n = len(slices)
    for k, prof in enumerate(slices):
        t = k / max(n - 1, 1)
        prof = np.nan_to_num(prof, nan=y0 - 1)
        clip(ax.fill_between(X, y0 - 1, prof, color=s.line_fill, lw=0, zorder=2 + 2 * k))
        clip(ax.plot(X, prof, color=s.ink, lw=0.3 + 0.55 * t, alpha=0.16 + 0.74 * t, zorder=3 + 2 * k)[0])
    clip(ax.plot(X, np.nan_to_num(skyline, nan=y0 - 1), color=s.ink, lw=0.9, alpha=0.95, zorder=3 + 2 * n)[0])


def _terrain_night(ax, fig, X, bands, sky_strip, y0: float, s: PanoramaStyle):
    """Dusk: a glow that fades upward from just above the skyline, black ridges, rim light on every crest."""
    clip = _Zone(ax, y0)
    pos = ax.get_position()
    W = round(pos.width * fig.get_figwidth() * fig.dpi)
    H = round(pos.height * fig.get_figheight() * fig.dpi)
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    ys = np.linspace(ylim[1], ylim[0], H)
    y_glow = float(np.nanmax(sky_strip)) + 0.15
    strength = np.where(ys >= y_glow, np.exp(-(((ys - y_glow) / s.glow_sigma) ** 2)), 1.0) * (ys >= y0)
    up = np.clip((ys - ylim[0]) / (ylim[1] - ylim[0]), 0, 1)
    g0, g1, g2 = (np.asarray(to_rgb(c)) for c in (s.night_ground, s.glow, s.sky_top))
    base = g0[None, :] + (g2 - g0)[None, :] * up[:, None]
    sky = np.empty((H, W, 3))
    sky[...] = (base + (g1[None, :] - base) * strength[:, None])[:, None, :]
    ax.imshow(sky, extent=[xlim[0], xlim[1], ylim[0], ylim[1]], aspect="auto", interpolation="bilinear", origin="upper", zorder=0)
    n = len(bands)
    for k, prof in enumerate(bands):
        t = k / max(n - 1, 1)
        prof = np.nan_to_num(prof, nan=y0 - 1)
        clip(ax.fill_between(X, y0 - 1, prof, color=_mix(s.night_far, s.night_near, t**1.15), lw=0, zorder=2 + 2 * k))
        clip(ax.plot(X, prof, color=s.rim, lw=0.6, alpha=0.42 - 0.3 * t, zorder=3 + 2 * k)[0])
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)


# ---------------------------------------------------------------- the sheets and the hero


def sheet(
    sky: Skyline,
    lon: float,
    lat: float,
    peaks,
    out_png: str | Path,
    *,
    strips=((0.0, 90.0), (90.0, 180.0)),
    treatment: str = "table",
    title: str,
    lines=(),
    style: PanoramaStyle | None = None,
) -> Path:
    """Stacked azimuth strips at one vertical scale, a title block above, a bearing scale under each.

    `strips` are (from, to) azimuth pairs, all of the same span so the horizontal scale is shared. A strip
    with no named summit is drawn short. `treatment` is "table" (the Result sheets) or "lines" (Method).
    """
    if treatment not in ("table", "lines"):
        raise ValueError(f"treatment must be 'table' or 'lines', not {treatment!r}")
    s = style or DEFAULT
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    tg = targets(sky, lon, lat, peaks)
    X, SKYC = sky.closed()
    bands = _profiles(sky, s.line_edges_km if treatment == "lines" else s.band_edges_km)
    finite = sky.skyline[np.isfinite(sky.skyline)]
    y0 = (np.floor(float(finite.min()) * 2) / 2 - 0.3) if finite.size else -3.0
    marks = _Marks(s.ink, s.muted, s.muted, s.muted, s.accent, s.paper, s.paper, s.ink)

    def in_strip(a0, a1, last):
        return tg[(tg["az"] >= a0) & ((tg["az"] <= a1) if last else (tg["az"] < a1))]

    ratios = [1.0 if len(in_strip(a0, a1, i == len(strips) - 1)) else s.empty_strip_ratio for i, (a0, a1) in enumerate(strips)]
    title_h = _title_height_in(s, len(lines))
    fig_h = sheet_height_in(s, ratios, len(lines))
    fig = plt.figure(figsize=(s.width_in, fig_h), dpi=s.dpi, facecolor=s.paper)
    left, right = s.margin, 1 - s.margin
    y = 1 - title_h / fig_h
    for i, ((a0, a1), r) in enumerate(zip(strips, ratios)):
        h = s.strip_in * r / fig_h
        ax = fig.add_axes([left, y - h, right - left, h])
        y -= h + s.gap_in / fig_h
        pxx = (right - left) * s.width_in * s.dpi / (a1 - a0)
        pxy = s.exaggeration * pxx
        ax.set_xlim(a0, a1)
        ax.set_ylim(y0 - s.scale_room, y0 - s.scale_room + s.strip_in * r * s.dpi / pxy)
        ax.set_axis_off()
        sel = (X >= a0 - 1e-9) & (X <= a1 + 1e-9)
        _level_line(ax, a0, a1, SKYC[sel], s, hair=s.hair, muted=s.muted)
        if treatment == "table":
            _terrain_table(ax, X[sel], [b[sel] for b in bands], y0, s)
        else:
            _terrain_lines(ax, X[sel], [b[sel] for b in bands], SKYC[sel], y0, s)
        pk = in_strip(a0, a1, i == len(strips) - 1)
        strip_max = np.nanmax(SKYC[sel]) if np.isfinite(SKYC[sel]).any() else 0.0
        _labels(ax, fig, pk, a0, a1, float(strip_max) + s.label_lift, s, marks, name_size=s.name_size, sub_size=s.sub_size, marker=s.marker)
        _scale(ax, fig, a0, a1, y0 - 0.12, s, ink=s.ink, muted=s.muted, hair=s.hair, num_size=7.2, comp_size=8.8)
    _title_block(fig, s, title=title, lines=list(lines), ink=s.ink, muted=s.muted, left=left, right=right)
    fig.savefig(out_png, dpi=s.dpi, facecolor=s.paper)
    plt.close(fig)
    return out_png


def hero(
    sky: Skyline,
    lon: float,
    lat: float,
    peaks,
    out_png: str | Path,
    *,
    title: str,
    subtitle: str,
    azimuths: tuple[float, float] | None = None,
    style: PanoramaStyle | None = None,
) -> Path:
    """The nocturne at 16:9 (2400 by 1350 px at the default dpi): one strip, the title set in the sky.

    `azimuths` is the (from, to) window; None picks the `hero_span` window with the most summits in view.
    `subtitle` may carry `{from_dir}` and `{to_dir}`, filled with the window's compass words.
    """
    s = style or DEFAULT
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    a0, a1 = azimuths or richest_window(sky, lon, lat, peaks, s.hero_span)
    tg = targets(sky, lon, lat, peaks)
    tg = tg[(tg["az"] >= a0) & (tg["az"] < a1)]
    X, SKYC = sky.closed()
    sel = (X >= a0 - 1e-9) & (X <= a1 + 1e-9)
    bands = _profiles(sky, s.band_edges_km)
    strip = SKYC[sel]
    y_lo = float(np.nanmin(strip)) - 0.35 if np.isfinite(strip).any() else -3.0
    y_hi = float(np.nanmax(strip)) if np.isfinite(strip).any() else 0.0

    fig = plt.figure(figsize=(16, 9), dpi=s.dpi, facecolor=s.night_ground)
    left, right, bottom, top = 0.03, 0.97, 0.035, 0.985
    ax = fig.add_axes([left, bottom, right - left, top - bottom])
    pxx = (right - left) * 16 * s.dpi / (a1 - a0)
    pxy = s.hero_exaggeration * pxx
    ax.set_xlim(a0, a1)
    ax.set_ylim(y_lo - s.scale_room * 0.9, y_lo - s.scale_room * 0.9 + (top - bottom) * 9 * s.dpi / pxy)
    ax.set_axis_off()
    _terrain_night(ax, fig, X[sel], [b[sel] for b in bands], strip, y_lo, s)
    ax.scatter(tg.loc[tg["vis"], "az"], tg.loc[tg["vis"], "ang"], s=s.hero_marker * 4.6, c=[s.night_accent], alpha=0.16, lw=0, zorder=9)
    marks = _Marks(s.night_ink, "#8E948C", s.night_muted, "#8E948C", s.night_accent, s.night_ground, s.night_ground, s.night_muted)
    _labels(ax, fig, tg, a0, a1, y_hi + 0.5, s, marks, name_size=s.hero_name_size, sub_size=s.hero_sub_size, marker=s.hero_marker)
    _scale(ax, fig, a0, a1, y_lo - 0.1, s, ink=s.night_ink, muted=s.night_muted, hair=s.night_hair, num_size=7.6, comp_size=9.5)

    n_v, n_h = int(tg["vis"].sum()), int((~tg["vis"]).sum())
    words = {"from_dir": COMPASS_WORDS[compass(a0)], "to_dir": COMPASS_WORDS[compass(a1)]}
    serif, sans = s.serif_family, s.sans_family
    fig.text(left + 0.012, 0.955, title, fontsize=34, fontfamily=serif, color=s.night_ink, va="top")
    fig.text(left + 0.012, 0.892, subtitle.format(**words), fontsize=11.5, fontfamily=sans, color=s.night_muted, va="top")
    lx, ly, r = left + 0.017, 0.858, 0.0042
    fig.patches.append(Ellipse((lx, ly), 2 * r, 2 * r * 16 / 9, transform=fig.transFigure, color=s.night_accent, zorder=20))
    fig.text(lx + 0.011, ly, f"{n_v} named summits in view", fontsize=10.5, fontfamily=sans, color=s.night_ink, va="center")
    lx2 = lx + 0.20
    fig.patches.append(Ellipse((lx2, ly), 2 * r, 2 * r * 16 / 9, transform=fig.transFigure, facecolor=s.night_ground, edgecolor=s.night_muted, lw=1.2, zorder=20))
    fig.text(lx2 + 0.011, ly, f"{n_h} behind a nearer ridge", fontsize=10.5, fontfamily=sans, color=s.night_muted, va="center")
    fig.text(right - 0.012, 0.955, s.source.replace(" · purespatial.com", "\npurespatial.com"), fontsize=8.2, fontfamily=sans, color=s.night_muted, va="top", ha="right", linespacing=1.5)
    fig.savefig(out_png, dpi=s.dpi, facecolor=s.night_ground)
    plt.close(fig)
    return out_png
