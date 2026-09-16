# purespatial-notebooks

The analyses behind purespatial.com posts. An agent does the modeling here; the author supplies direction, the field check, and QA. The site repository (`../pure-spatial`) turns a finished folder into a post with `/write-post <slug>`; its `docs/writing-posts.md` is the other half of this contract.

The author's own guide is `docs/author-guide.md`; when the author asks how to do something here, point at it and keep it current.

## Skill routing

- Run an analysis, start a post's notebook, "run a viewshed from X", "re-run with Y" → invoke /analyze
- Turn a finished folder into the site post → `/write-post <slug>` in `../pure-spatial`

## The four tests

Every folder here passes all four or it does not exist: open data (public, no account), open tools, a named public fire, route, or landscape, and a result that is scored or field-checked against something the model did not see. Modeling alone is not a result.

## Layout

- `purespatial/`: shared tools. `dem` (3DEP via py3dep, projected GeoTIFFs), `viewshed` (gdal_viewshed), `peaks` (USGS GNIS summits), `score` (predictions against observations, the result sentence), `figures`, `result` (result.json). Tested in `tests/`; every helper change lands with its test.
- `<slug>/`: one post, named exactly as the site post folder. `params.py` (the constants), `fetch.py` (public inputs into `data/`), `notebook.py` (jupytext percent format, the source of truth), `notebook.ipynb` (executed by `make run`, outputs saved, committed), `figures/*.png`, `peaks.geojson` (or another small GeoJSON of the rated targets), `field/observations.csv` and `field/photos/`, `result.json`, `README.md`.
- `data/` anywhere is gitignored. Rasters, point clouds, and zips never enter the repository; `fetch.py` refills them.

## Rules the agent keeps

- Edit `notebook.py`, never `notebook.ipynb`; `make run SLUG=<slug>` regenerates the notebook with outputs. Commit both.
- Every number in `result.json` and every figure comes from a cell that ran. No number is typed by hand.
- In `field/observations.csv` the columns `observed`, `photo`, and `note` belong to the author: the notebook reads them back and writes them untouched on every run while it refreshes the model's columns. Never edit them, and never let code overwrite them.
- `result.json` carries `field_check.status`. While it is `pending`, the folder is not a post yet: stop, push, and tell the author what to fill in. Draft the site post only from a `scored` result.
- Public data only, no credentials, no paid services. If a source needs an account, say so and stop.
- Open tools only: GDAL, Python packages on PyPI, USGS and NASA services.
- Figures: PNG, at least 2000 px on the long side, one tint on a grey hillshade, named things labeled without overlap. The hero is 16:9. Every visual choice is a `Style` field (`purespatial/figures.py`), overridden per post in `params.py`; a taste change is a knob, not a code edit.
- The skyline panorama (`purespatial/panorama.py`) has three treatments, chosen on the 2026-09-16 design board and not to be reopened per post: `table` sheets (east and west, two quarter-turns each) for Result, `lines` for Method, the `nocturne` hero. Its knobs are `PanoramaStyle`; the site's type (Charter, Avenir Next) and DESIGN.md tokens are its defaults. Design a figure for the width a post shows it at (about 700 px); forty labels never fit in one image.
- Voice for anything that reaches the site (captions, the result sentence): first person, present tense, plain nouns, no exclamation marks, what happened then what to do next.

## Environment

Poetry with an in-project virtualenv on the Homebrew Python 3.14; GDAL from Homebrew provides `gdal_viewshed`. `make install`, `make test`, `make lint`. Poetry lives at `~/.local/bin/poetry`.
