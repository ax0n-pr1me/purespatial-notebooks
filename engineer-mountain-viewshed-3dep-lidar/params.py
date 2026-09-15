"""Constants for the Engineer Mountain viewshed. fetch.py and notebook.py import these; nothing else defines them."""

SLUG = "engineer-mountain-viewshed-3dep-lidar"
STATE = "CO"
SUBJECT_NAME = "Engineer Mountain"
# Two Colorado summits carry this name. This is the one above Coal Bank Pass on US 550,
# San Juan County; the hint picks it over the Engineer Pass namesake near Ouray.
NEAR_HINT = (-107.79, 37.70)
REGION = "Colorado"

DATASETS = ["3dep-lidar"]

# Far field: the 1/3 arc-second seamless DEM resampled to 30 m, 60 km around the summit.
FAR_RADIUS_M = 60_000
FAR_RES_M = 30
# Near field: 1 m lidar where the 3DEP project covers it, 3 km around the summit.
NEAR_RADIUS_M = 3_000
NEAR_RES_M = 1

OBSERVER_HEIGHT_M = 1.7  # eye height standing on the summit cell
MIN_PEAK_ELEVATION_M = 3_600  # named summits this high or higher are candidates
MIN_PEAK_DISTANCE_KM = 1.0
MAX_PEAKS = 40
