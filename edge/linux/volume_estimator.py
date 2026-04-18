"""
Estimates trash item volume from its bounding box (pixels) and distance (mm).

Uses the pinhole camera model:
    real_size_mm = pixel_size * dist_mm / focal_length_px

Volume is approximated as a rectangular prism W × H × D, where depth D is
estimated as min(W, H) × 0.6 — a conservative heuristic that works reasonably
well for compact household items (bottles, cans, food containers).

Calibrate focal_length_px once per camera:
    focal_length_px = (object_width_px * known_dist_mm) / known_real_width_mm
"""
from __future__ import annotations

_MM3_TO_LITERS = 1e-6


class VolumeEstimator:
    def __init__(self, focal_length_px: float, depth_ratio: float = 0.6):
        self._f = focal_length_px
        self._depth_ratio = depth_ratio

    def estimate(self, bbox: tuple[int, int, int, int], dist_mm: float) -> float:
        """Return estimated volume in liters. Returns 0.0 if inputs are invalid."""
        if dist_mm <= 0 or self._f <= 0:
            return 0.0

        _x, _y, bbox_w_px, bbox_h_px = bbox
        real_w = (bbox_w_px * dist_mm) / self._f
        real_h = (bbox_h_px * dist_mm) / self._f
        real_d = min(real_w, real_h) * self._depth_ratio

        return real_w * real_h * real_d * _MM3_TO_LITERS
