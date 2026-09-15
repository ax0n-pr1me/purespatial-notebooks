# purespatial-notebooks

The analyses behind purespatial.com posts. An agent does the modeling here; the author supplies direction, the field check, and QA. The site repository (`../pure-spatial`) turns a finished folder into a post with `/write-post <slug>`; its `docs/writing-posts.md` is the other half of this contract.

## Skill routing

- Run an analysis, start a post's notebook, "run a viewshed from X", "re-run with Y" → invoke /analyze
- Turn a finished folder into the site post → `/write-post <slug>` in `../pure-spatial`

## The four tests

Every folder here passes all four or it does not exist: open data (public, no account), open tools, a named public fire, route, or landscape, and a result that is scored or field-checked against something the model did not see. Modeling alone is not a result.

## Layout

- `purespatial/`: shared tools. `dem` (3DEP via py3dep, projected GeoTIFFs), `viewshed` (gdal_viewshed), `peaks` (USGS GNIS summits), `score` (predictions against observations, the result sentence), `figures`, `result` (result.json). Tested in `tests/`; every helper change lands with its test.
- `<slug>/`: one post, named exactly as the site post folder. `params.py` (the constants), `fetch.py` (public inputs into `data/`), `notebook.py` (jupytext percent format, the source of truth), `notebook.ipynb` (executed by `make run`, outputs saved, committed), `figures/*.png`, `field/observations.csv` and `field/photos/`, `result.json`, `README.md`.
- `data/` anywhere is gitignored. Rasters, point clouds, and zips never enter the repository; `fetch.py` refills them.

## Rules the agent keeps

- Edit `notebook.py`, never `notebook.ipynb`; `make run SLUG=<slug>` regenerates the notebook with outputs. Commit both.
- Every number in `result.json` and every figure comes from a cell that ran. No number is typed by hand.
- `field/observations.csv` is written once by the notebook as a template and then belongs to the author. Never overwrite or edit filled rows. The notebook reads it and scores.
- `result.json` carries `field_check.status`. While it is `pending`, the folder is not a post yet: stop, push, and tell the author what to fill in. Draft the site post only from a `scored` result.
- Public data only, no credentials, no paid services. If a source needs an account, say so and stop.
- Open tools only: GDAL, Python packages on PyPI, USGS and NASA services.
- Figures: PNG, at least 2000 px on the long side, one accent tint on a grey hillshade, named things labeled. The hero is 16:9.
- Voice for anything that reaches the site (captions, the result sentence): first person, present tense, plain nouns, no exclamation marks, what happened then what to do next.

## Environment

Poetry with an in-project virtualenv on the Homebrew Python 3.14; GDAL from Homebrew provides `gdal_viewshed`. `make install`, `make test`, `make lint`. Poetry lives at `~/.local/bin/poetry`.
