"""Spatial framework for F4/M3.

Heavy geospatial dependencies are imported lazily by submodules.
"""

SOURCE_CRS = "EPSG:4326"
METRIC_WORKING_CRS = "EPSG:25833"

__all__ = ["METRIC_WORKING_CRS", "SOURCE_CRS"]
