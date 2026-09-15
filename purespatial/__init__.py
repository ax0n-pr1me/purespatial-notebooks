"""Shared tools behind purespatial.com posts: open data in, a scored result out.

Modules
  dem       3DEP elevation models around a point, projected GeoTIFFs, cached in data/
  viewshed  gdal_viewshed with the observer given in WGS84
  peaks     named summits from USGS GNIS, bearings and distances from an observer
  score     predictions against field observations; the one result sentence
  figures   hillshade, viewshed tint, labeled peaks, in the site's manner
  result    result.json, the hand-off the site's /write-post reads
"""

from . import dem, figures, peaks, result, score, viewshed

__all__ = ["dem", "figures", "peaks", "result", "score", "viewshed"]
