"""Small geospatial helpers (field boundary checks, EUDR-style polygon validation)."""
import math

import numpy as np
from shapely.geometry import Point, Polygon

M_PER_DEG = 111_320.0
KENYA_BBOX = (33.9, -4.8, 41.95, 5.1)  # lon_min, lat_min, lon_max, lat_max


def present(x):
    return x is not None and not (isinstance(x, float) and np.isnan(x))


def to_poly(pairs):
    """pairs: [(lon, lat), ...] -> Polygon or None when fewer than 3 distinct vertices."""
    if not pairs or len(set(pairs)) < 3:
        return None
    return Polygon(pairs)


def area_ha(poly):
    lat = poly.centroid.y
    return poly.area * (M_PER_DEG ** 2) * math.cos(math.radians(lat)) / 10_000


def distance_m(pt, poly):
    return poly.distance(Point(pt)) * M_PER_DEG


def in_bbox(lon, lat, bbox=KENYA_BBOX):
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]
