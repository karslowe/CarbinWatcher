"""
Assigns a bin type to a detected item based on the horizontal position of
its bounding-box centroid relative to the camera frame.

The camera is expected to face two bins side-by-side:
  left half  → BIN_LEFT  (default "recycle")
  right half → BIN_RIGHT (default "landfill")

The split point is configurable via FRAME_SPLIT_RATIO (default 0.5).
"""
from __future__ import annotations


class BinDetector:
    def __init__(
        self,
        frame_width: int,
        bin_left: str = "recycle",
        bin_right: str = "landfill",
        split_ratio: float = 0.5,
    ):
        self._frame_width = frame_width
        self._bin_left = bin_left
        self._bin_right = bin_right
        self._split_x = int(frame_width * split_ratio)

    def assign_bin(self, bbox: tuple[int, int, int, int]) -> str:
        """Return which bin the item is in based on bbox centroid x."""
        x, _y, w, _h = bbox
        center_x = x + w // 2
        return self._bin_left if center_x < self._split_x else self._bin_right
