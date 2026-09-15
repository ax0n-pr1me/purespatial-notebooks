---
name: analyze
description: Run or re-run the analysis behind one purespatial post, from a one-line brief such as "run a viewshed from the top of Engineer Mountain" to a pushed notebook folder with figures, a predictions table for the field check, and result.json; then hand off to the site's /write-post once the result is scored.
---

# /analyze <slug> "<brief>"

You do the modeling; the author directs, supplies the field check, and reviews. Read `CLAUDE.md` in this repository first, then the model folder `engineer-mountain-viewshed-3dep-lidar/`.

## Inputs to settle before code

From the brief, the existing folders, and public sources. Ask only for what is missing.

- **Slug**: lowercase, hyphens, equal to the site post folder. Check `../pure-spatial/src/content/posts/` and this repository for a clash.
- **Subject**: a named public fire, route, or landscape with coordinates you can verify (GNIS for US places; a public incident record for fires). Namesakes exist; pick with a `near` hint and say which one.
- **Question and method**: what is modeled, with which open tool, at what resolution and radius. Name the datasets by their site hub slug (`../pure-spatial/src/content/datasets/`). A dataset with no hub means the post will need one; note it for `/write-post`.
- **The check**: what observation the model did not see will score it, and who supplies it. Default for terrain posts: the author's photographs and a `field/observations.csv` you generate. Without a check there is no post; say so.

## Steps

1. `git switch -c analysis/<slug>` from an up-to-date `main`. Copy the model folder's shape: `params.py`, `fetch.py`, `notebook.py`, `README.md`, `field/photos/.gitkeep`.
2. Put every constant in `params.py`; `fetch.py` and `notebook.py` import it.
3. Use `purespatial.*` before writing new code. A new helper goes into the package with a test in `tests/`, not into the notebook.
4. `make fetch SLUG=<slug>` then `make run SLUG=<slug>`. Fix what fails. Keep the run under about ten minutes on this machine; shrink the radius or coarsen the far field before you reach for more compute.
5. Read the outputs as a reviewer would: does the figure show what the caption says, are the predictions plausible (a 4000 m peak 3 km away should be visible), does `result.json` validate.
6. `make test` and `make lint` green. Commit `notebook.py`, `notebook.ipynb`, `figures/`, `field/observations.csv`, `result.json`, `README.md`, `params.py`, `fetch.py`. Never `data/`.
7. Push the branch and open a pull request with `gh pr create` describing the method, the inputs, and what the author must fill in. Do not merge.

## The field-check gate

If `result.json` says `field_check.status: pending`, stop here and report:

- the pull request URL,
- the path of `field/observations.csv` and how many rows want a `visible` or `hidden`,
- where photos go (`field/photos/`, JPEG, at most 2000 px, named in the `photo` column),
- the command that scores it once filled: `make run SLUG=<slug>`.

When the author has filled it, re-run `make run`, confirm `status: scored`, commit, and continue.

## Hand-off to the site

With a scored result: in `../pure-spatial`, follow `.claude/skills/write-post/SKILL.md` for the same slug. `result.json` supplies `result`, `subject`, `datasets`, `findings`, and the figure list; `figures/hero.png` is the hero source. The Why section still comes from the author's notes.

## Report

Method in three sentences, the inputs and their sources, the run time, the predictions summary (how many visible, how many hidden, the farthest visible), what is pending, and the pull request URL.
