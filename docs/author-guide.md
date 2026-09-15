# Author guide

How you work with this repository. The agent's rules are in `CLAUDE.md` and `.claude/skills/analyze/SKILL.md`; the site's post contract is `docs/writing-posts.md` in `pure-spatial`. This page is yours: what to say, what you do, and how to change what comes out.

## The division of labour

| You | The agent |
|---|---|
| Name the subject and the question in one line | Finds the subject in public data, settles method and datasets, says which namesake it picked |
| Supply the check the model did not see: photographs, a track, an incident record | Fetches inputs, runs the model, rates every named target, writes `field/observations.csv` |
| Fill `observed` in that CSV; drop photos in `field/photos/` | Scores the filled rows, writes `result.json`, pushes a branch and pull request |
| Open the rasters in QGIS and look | Fixes what you point at, re-runs in seconds |
| Write the Why section from your own experience | Drafts the rest of the post from `result.json` with `/write-post`, never merges |
| Review the Vercel preview, merge on Tuesday, send the email | Runs the checks and the canary |

## Briefs that work

Open Claude Code in this folder and say what you want in plain words. The `/analyze` skill fills in the rest and asks only for what it cannot find.

```
/analyze engineer-mountain-viewshed-3dep-lidar "run a viewshed from the top of Engineer Mountain"
/analyze <slug> "slope and aspect from 3DEP along the <fire> perimeter against the public progression, category fire"
/analyze <slug> "re-run Engineer with a 100 km far field and label 30 peaks"
```

A brief needs a named public place, fire, or route, and a check. "Make a pretty map of the San Juans" is not a post; "which named peaks can a camera on Engineer see, checked against my summit photos" is.

## Changing the analysis or the images

Every run is cached: the DEMs and names file live in `data/`, so a re-run is the viewshed and the figures, under ten seconds. Three levels, cheapest first.

1. **Say it.** "The labels are crowded", "the viewshed is too faint", "use a 100 km radius", "drop peaks under 4000 m". The agent changes a knob or a line, re-runs `make run`, and shows you the figure. This is the normal path.
2. **Turn a knob yourself.** Every visual choice is a field on `Style` in `purespatial/figures.py`, overridden per post in `params.py`:
   ```python
   from purespatial.figures import Style
   STYLE = Style(label_top=15, tint_alpha=0.85, hillshade_low=-0.6)
   ```
   Radii, resolutions, elevation thresholds, and the peak count are the other constants in `params.py`. Then:
   ```bash
   make run SLUG=engineer-mountain-viewshed-3dep-lidar
   ```
3. **Change the method.** New code goes into `purespatial/` with a test in `tests/`, and the post's `notebook.py` calls it. Ask the agent; `make test` and `make lint` must stay green.

Never edit `notebook.ipynb`; it is regenerated from `notebook.py` every run.

## QA in QGIS

Everything the notebook made is on disk in the post folder:

- `data/dem_30m_60km.tif`, `data/dem_1m_3km.tif`: the DEMs, EPSG:32613 (UTM 13N), metres, nodata -9999.
- `data/viewshed_far.tif`, `data/viewshed_near.tif`: 255 where the ground is in view, 0 where it is not, same grid as their DEM, cropped to the radius.
- `peaks.geojson`: the rated peaks and the observer, WGS84, with `predicted`, `elevation_m`, `distance_km`, `bearing_deg`.
- `field/observations.csv`: the same peaks as a table; QGIS loads it as a delimited text layer on `lon`, `lat`.

If a rating looks wrong in QGIS, say which peak; the agent checks the line of sight and either fixes the method or explains the terrain.

## The field check

1. Open `field/observations.csv`. One row per rated peak, sorted by bearing, with the model's `predicted`.
2. From your photographs, write `visible` or `hidden` in `observed` for every peak you can judge. Leave the rest blank; blank rows are not scored. Name the photo in `photo`, add anything worth saying in `note`.
3. Put the photographs in `field/photos/`, JPEG, at most 2000 px on the long side. They are yours; the repository is public.
4. `make run SLUG=<slug>`. `result.json` turns `scored` and carries the result sentence. Commit and push.

Your columns (`observed`, `photo`, `note`) survive every run; the model's columns refresh, and the run prints any rating that changed since the last one. To start over, delete the CSV and run again.

## Publishing

In `pure-spatial`: `/write-post <slug>` drafts the post from `result.json` and the figures; you write the Why section. Review the Vercel preview, run the checks, and `/land-and-deploy` on Tuesday. Then one email in Buttondown with the result sentence, a figure, and the post link with `?ref=email`.

## Commands

```bash
make install                 # once per machine (Poetry, in-project .venv)
make test                    # the package tests
make lint                    # ruff
make fetch SLUG=<slug>       # download that post's inputs into data/
make run   SLUG=<slug>       # execute notebook.py, write notebook.ipynb, figures, result.json
make clean-run SLUG=<slug>   # drop viewsheds, figures, result.json; keep DEMs and field/
```

Poetry is at `~/.local/bin/poetry`; `gdal_viewshed` comes from Homebrew GDAL.
