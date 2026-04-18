"""
YOLOv8x ONNX inference wrapper.

Expected ONNX output shape: [1, num_classes+4, 8400] (YOLOv8 default export).
YOLOv8x (~68 MB ONNX, ~1.5–2 GB RAM) is the largest YOLOv8 variant and fits
within the 4 GB RAM budget of the Arduino UNO Q for CPU inference.
Post-processing applies confidence filtering + NMS and returns a flat
list of Detection dicts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np
import onnxruntime as ort

# ---------------------------------------------------------------------------
# Label → bin-category mapping
# ---------------------------------------------------------------------------
LABEL_TO_CATEGORY: dict[str, str] = {
    "plastic_bottle": "recycle",
    "glass_bottle": "recycle",
    "metal_can": "recycle",
    "cardboard": "recycle",
    "paper": "recycle",
    "newspaper": "recycle",
    "aluminum_foil": "recycle",
    "beverage_carton": "recycle",
    "food_waste": "compost",
    "fruit_peel": "compost",
    "coffee_grounds": "compost",
    "eggshell": "compost",
    "styrofoam": "landfill",
    "plastic_bag": "landfill",
    "straw": "landfill",
    "tissue": "landfill",
    "chip_bag": "landfill",
    "dirty_container": "landfill",
    "battery": "hazardous",
    "electronics": "hazardous",
}


@dataclass
class Detection:
    label: str
    category: str
    confidence: float
    # (x, y, w, h) in pixels — top-left origin
    bbox: tuple[int, int, int, int]


class TrashDetector:
    _INPUT_SIZE = 640  # YOLOv8 default

    def __init__(self, model_path: str, labels_path: str, threshold: float = 0.45):
        self.threshold = threshold
        self.labels: list[str] = Path(labels_path).read_text().strip().splitlines()

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            model_path,
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name

    # ------------------------------------------------------------------
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run inference on a BGR frame; return filtered + NMS detections."""
        h_orig, w_orig = frame.shape[:2]
        blob, scale, pad = self._preprocess(frame)

        raw = self._session.run(None, {self._input_name: blob})[0]  # [1, nc+4, 8400]
        return self._postprocess(raw, scale, pad, w_orig, h_orig)

    # ------------------------------------------------------------------
    def _preprocess(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray, float, tuple[int, int]]:
        s = self._INPUT_SIZE
        h, w = frame.shape[:2]
        scale = min(s / w, s / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        pad_x = (s - new_w) // 2
        pad_y = (s - new_h) // 2
        canvas = np.full((s, s, 3), 114, dtype=np.uint8)
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized

        blob = canvas[:, :, ::-1].astype(np.float32) / 255.0  # BGR→RGB, normalise
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis]       # HWC→1CHW
        return blob, scale, (pad_x, pad_y)

    def _postprocess(
        self,
        raw: np.ndarray,
        scale: float,
        pad: tuple[int, int],
        orig_w: int,
        orig_h: int,
    ) -> list[Detection]:
        # raw shape: [1, 4+num_classes, num_anchors]
        pred = raw[0].T  # [num_anchors, 4+num_classes]
        num_classes = pred.shape[1] - 4

        boxes_cx = pred[:, 0]
        boxes_cy = pred[:, 1]
        boxes_w  = pred[:, 2]
        boxes_h  = pred[:, 3]
        class_scores = pred[:, 4:]  # [num_anchors, num_classes]

        confidences = class_scores.max(axis=1)
        class_ids   = class_scores.argmax(axis=1)

        mask = confidences >= self.threshold
        if not mask.any():
            return []

        confidences = confidences[mask]
        class_ids   = class_ids[mask]
        cx = boxes_cx[mask]
        cy = boxes_cy[mask]
        bw = boxes_w[mask]
        bh = boxes_h[mask]

        # Convert from padded/scaled coords back to original frame pixels
        pad_x, pad_y = pad
        x1 = ((cx - bw / 2) - pad_x) / scale
        y1 = ((cy - bh / 2) - pad_y) / scale
        x2 = ((cx + bw / 2) - pad_x) / scale
        y2 = ((cy + bh / 2) - pad_y) / scale

        x1 = np.clip(x1, 0, orig_w).astype(int)
        y1 = np.clip(y1, 0, orig_h).astype(int)
        x2 = np.clip(x2, 0, orig_w).astype(int)
        y2 = np.clip(y2, 0, orig_h).astype(int)

        # NMS per class
        results: list[Detection] = []
        for cls in np.unique(class_ids):
            idx = np.where(class_ids == cls)[0]
            boxes_cls  = np.stack([x1[idx], y1[idx], x2[idx], y2[idx]], axis=1).astype(float)
            scores_cls = confidences[idx]

            keep = cv2.dnn.NMSBoxes(
                bboxes=boxes_cls[:, :2].tolist(),  # cv2 wants x,y,w,h
                scores=scores_cls.tolist(),
                score_threshold=self.threshold,
                nms_threshold=0.45,
            )
            if keep is None:
                continue
            keep = keep.flatten() if hasattr(keep, "flatten") else keep

            for k in keep:
                bx1, by1, bx2, by2 = int(x1[idx[k]]), int(y1[idx[k]]), int(x2[idx[k]]), int(y2[idx[k]])
                label = self.labels[cls] if cls < len(self.labels) else "unknown"
                results.append(
                    Detection(
                        label=label,
                        category=LABEL_TO_CATEGORY.get(label, "landfill"),
                        confidence=float(scores_cls[k]),
                        bbox=(bx1, by1, bx2 - bx1, by2 - by1),
                    )
                )

        return results
