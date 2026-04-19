"""
CarbinWatcher edge — main detection loop.

Start with:
    python main.py           # real hardware
    python main.py --sim     # laptop simulation (no Arduino needed)

Required env vars (see config.py for full list):
    GEMINI_API_KEY, S3_BUCKET, SERIAL_PORT, MODEL_PATH, LABELS_PATH
    BIN_LEFT, BIN_RIGHT  (which bin is on each side of the frame)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import cv2

from bin_detector import BinDetector
from bin_verifier import BinVerifier
from config import Config
from mqtt_publisher import MqttPublisher
from model_runner import TrashDetector
from serial_comms import SerialComms
from volume_estimator import VolumeEstimator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("carbinwatcher")


def _open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(Config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {Config.CAMERA_INDEX}")
    return cap


def run(sim: bool = False) -> None:
    detector  = TrashDetector(Config.MODEL_PATH, Config.LABELS_PATH, Config.CONFIDENCE_THRESHOLD)
    bin_det   = BinDetector(Config.FRAME_WIDTH, Config.BIN_LEFT, Config.BIN_RIGHT)
    estimator = VolumeEstimator(Config.FOCAL_LENGTH_PX)
    verifier  = BinVerifier(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)
    publisher = MqttPublisher(
        iot_endpoint=Config.IOT_ENDPOINT,
        thing_name=Config.THING_NAME,
        cert_path=Config.IOT_CERT_PATH,
        key_path=Config.IOT_KEY_PATH,
        root_ca_path=Config.IOT_ROOT_CA_PATH,
        topic=Config.MQTT_TOPIC,
    )
    publisher.connect()

    if sim:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "sim"))
        from sim_serial import SimSerialComms
        serial = SimSerialComms(Config.SERIAL_PORT, Config.SERIAL_BAUD)
    else:
        serial = SerialComms(Config.SERIAL_PORT, Config.SERIAL_BAUD)

    cap = _open_camera()

    log.info(
        "CarbinWatcher started | bins: LEFT=%s RIGHT=%s | trigger=%.0fmm",
        Config.BIN_LEFT, Config.BIN_RIGHT, Config.TRIGGER_DIST_MM,
    )

    last_detection = 0.0

    try:
        while True:
            dist_mm = serial.latest_distance()
            now     = time.monotonic()

            # Wait for an item to break the distance threshold
            if dist_mm is None or dist_mm > Config.TRIGGER_DIST_MM:
                time.sleep(0.05)
                continue

            # Cooldown guard — avoid re-triggering on the same item
            if now - last_detection < Config.COOLDOWN_S:
                time.sleep(0.05)
                continue

            # Let the item settle before grabbing the frame
            time.sleep(Config.STABILIZE_MS / 1000.0)

            ret, frame = cap.read()
            if not ret:
                log.warning("Camera read failed — skipping frame")
                continue

            last_detection = time.monotonic()
            detections = detector.detect(frame)

            if not detections:
                log.info("No item classified in frame")
                continue

            # ---------------------------------------------------------------
            # Multiple items → ask user to separate them
            # ---------------------------------------------------------------
            if len(detections) > 1:
                labels = [d.label for d in detections]
                log.info("Multiple items detected (%s) — signaling split", labels)
                serial.send_command("LED:SPLIT")
                serial.send_command("BUZZ:2")
                time.sleep(2.0)
                serial.send_command("LED:OFF")
                continue

            # ---------------------------------------------------------------
            # Single item — classify, verify, feedback, publish
            # ---------------------------------------------------------------
            det = detections[0]
            detected_bin  = bin_det.assign_bin(det.bbox)
            volume_liters = estimator.estimate(det.bbox, dist_mm)
            is_correct, reason = verifier.verify(det.label, detected_bin)

            log.info(
                "item=%s  category=%s  conf=%.2f  bin=%s  correct=%s  vol=%.3fL  dist=%dmm",
                det.label, det.category, det.confidence,
                detected_bin, is_correct, volume_liters, dist_mm,
            )

            if is_correct:
                serial.send_command("LED:GREEN")
            else:
                serial.send_command("LED:RED")
                serial.send_command("BUZZ:3")

            publisher.publish({
                "ts":                 datetime.now(timezone.utc).isoformat(),
                "user_id":            Config.USER_ID,
                "thing_name":         Config.THING_NAME,
                "item":               det.label,
                "category":           det.category,
                "confidence":         round(det.confidence, 4),
                "volume_liters_est":  round(volume_liters, 4),
                "dist_mm":            int(dist_mm),
                "detected_bin":       detected_bin,
                "placement_correct":  is_correct,
                "reason":             reason,
            })

            time.sleep(2.0)
            serial.send_command("LED:OFF")

    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        cap.release()
        serial.close()
        publisher.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CarbinWatcher edge app")
    parser.add_argument("--sim", action="store_true", help="Run without Arduino (simulated distance + terminal LED/BUZZ output)")
    args = parser.parse_args()
    run(sim=args.sim)
