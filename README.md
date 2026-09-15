# purespatial-notebooks

The notebooks behind [purespatial.com](https://purespatial.com): open tools on open wildfire and terrain data, one folder per post, each with a result checked against something the model did not see.

Working here as the author: `docs/author-guide.md`.

## One post, one folder

```
<slug>/
  README.md          what the notebook shows and how to run it
  params.py          the constants: subject, radii, resolutions, thresholds
  fetch.py           downloads the public inputs into data/ (gitignored)
  notebook.py        the analysis, jupytext percent format; the source of truth
  notebook.ipynb     the same notebook executed top to bottom, outputs saved
  figures/           rendered PNGs
  peaks.geojson      rated targets and the observer, for QGIS and GitHub's map view
  field/             observations.csv and photos/: the field check
  result.json        the scored result the site post is drafted from
```

The folder name is the post's slug on the site; the post links here.

## Run one

```bash
brew install gdal                 # gdal_viewshed
pipx install poetry               # or your Poetry
make install
make test
make fetch SLUG=engineer-mountain-viewshed-3dep-lidar
make run   SLUG=engineer-mountain-viewshed-3dep-lidar
```

`make run` executes `notebook.py` in the post folder and writes `notebook.ipynb`, the figures, and `result.json`. Inputs are cached in `data/`; a second run does no downloading.

## Data

USGS 3D Elevation Program (public domain) through `py3dep`; USGS Geographic Names Information System (public domain). Each post's README names what it used. Photographs in `field/photos/` are the author's.

## License

Code: MIT. Data as licensed by its source. Photographs and text: all rights reserved.
