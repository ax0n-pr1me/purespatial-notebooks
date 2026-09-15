# Engineer Mountain viewshed, 3DEP

What the USGS 3D Elevation Program says can be seen from the summit of Engineer Mountain (the one above Coal Bank Pass, San Juan County, Colorado), scored against the summit photographs.

- Far field: 3DEP 1/3 arc-second seamless DEM resampled to 30 m, 60 km around the summit.
- Near field: 3DEP 1 m lidar bare-earth DEM, 3 km around the summit.
- Tool: `gdal_viewshed`, observer 1.7 m above the summit cell, curvature with standard refraction.
- Named peaks: USGS GNIS summits within 60 km at 3600 m or higher, the highest forty, each rated visible or hidden by the far viewshed.
- Check: `field/observations.csv`, one row per rated peak, `observed` filled from photographs; `result.json` carries the score.

Run from the repository root:

```bash
make fetch SLUG=engineer-mountain-viewshed-3dep-lidar
make run   SLUG=engineer-mountain-viewshed-3dep-lidar
```

Data: USGS 3DEP and USGS GNIS, public domain. Photographs: the author's.
