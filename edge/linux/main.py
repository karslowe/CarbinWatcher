"""
CarbinWatcher edge — main detection loop.

Start with:
    python main.py

Required env vars (see config.py for full list):
    GEMINI_API_KEY, S3_BUCKET, SERIAL_PORT, MODEL_PATH, LABELS_PATH
    BIN_LEFT, BIN_RIGHT  (which bin is on each side of the frame)
"""
from __future__ import annotations

import logging
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
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("carbinwatcher")


def _open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(Config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {Config.CAMERA_INDEX}")
    return cap


def run() -> None:
    log.debug("Initializing TrashDetector: model=%s labels=%s threshold=%.2f",
              Config.MODEL_PATH, Config.LABELS_PATH, Config.CONFIDENCE_THRESHOLD)
    detector  = TrashDetector(Config.MODEL_PATH, Config.LABELS_PATH, Config.CONFIDENCE_THRESHOLD)
    log.debug("TrashDetector ready")

    bin_det   = BinDetector(Config.FRAME_WIDTH, Config.BIN_LEFT, Config.BIN_RIGHT)
    estimator = VolumeEstimator(Config.FOCAL_LENGTH_PX)

    log.debug("Initializing BinVerifier (Gemini model=%s)", Config.GEMINI_MODEL)
    verifier  = BinVerifier(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)

    log.debug("Connecting to AWS IoT endpoint=%s topic=%s", Config.IOT_ENDPOINT, Config.MQTT_TOPIC)
    publisher = MqttPublisher(
        iot_endpoint=Config.IOT_ENDPOINT,
        thing_name=Config.THING_NAME,
        cert_path=Config.IOT_CERT_PATH,
        key_path=Config.IOT_KEY_PATH,
        root_ca_path=Config.IOT_ROOT_CA_PATH,
        topic=Config.MQTT_TOPIC,
    )
    publisher.connect()
    log.debug("MQTT connected")

    log.debug("Opening serial port=%s baud=%d", Config.SERIAL_PORT, Config.SERIAL_BAUD)
    serial = SerialComms(Config.SERIAL_PORT, Config.SERIAL_BAUD)

    log.debug("Opening camera index=%d (%dx%d)", Config.CAMERA_INDEX, Config.FRAME_WIDTH, Config.FRAME_HEIGHT)
    cap = _open_camera()
    log.debug("Camera opened")

    log.info(
        "CarbinWatcher started | bins: LEFT=%s RIGHT=%s | trigger=%.0fmm",
        Config.BIN_LEFT, Config.BIN_RIGHT, Config.TRIGGER_DIST_MM,
    )

    last_detection = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning("Camera read failed — skipping frame")
                time.sleep(0.05)
                continue

            display = frame.copy()

            dist_mm = serial.latest_distance()
            now     = time.monotonic()
            log.debug("Loop tick | dist=%s  cooldown_remaining=%.1fs",
                      f"{dist_mm:.0f}mm" if dist_mm is not None else "None",
                      max(0.0, Config.COOLDOWN_S - (now - last_detection)))

            triggered = (
                dist_mm is not None
                and dist_mm <= Config.TRIGGER_DIST_MM
                and now - last_detection >= Config.COOLDOWN_S
            )

            if not triggered and dist_mm is not None and dist_mm <= Config.TRIGGER_DIST_MM:
                log.debug("Distance triggered but still in cooldown — skipping")

            if triggered:
                log.debug("Trigger fired at dist=%.0fmm — stabilizing for %dms",
                          dist_mm, Config.STABILIZE_MS)
                time.sleep(Config.STABILIZE_MS / 1000.0)
                ret, frame = cap.read()
                if not ret:
                    log.warning("Camera read failed after stabilize — skipping trigger")
                    continue
                display = frame.copy()

                last_detection = time.monotonic()
                log.debug("Running inference...")
                detections = detector.detect(frame)
                log.debug("Inference complete — %d detection(s)", len(detections))

                if not detections:
                    log.info("No item classified in frame")
                elif len(detections) > 1:
                    # -------------------------------------------------------
                    # Multiple items → ask user to separate them
                    # -------------------------------------------------------
                    labels = [d.label for d in detections]
                    log.info("Multiple items detected (%s) — signaling split", labels)
                    for d in detections:
                        x, y, w, h = d.bbox
                        cv2.rectangle(display, (x, y), (x + w, y + h), (0, 165, 255), 2)
                        cv2.putText(display, d.label, (x, y - 6),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 1)
                    log.debug("Sending LED:SPLIT + BUZZ:2")
                    serial.send_command("LED:SPLIT")
                    serial.send_command("BUZZ:2")
                    time.sleep(2.0)
                    serial.send_command("LED:OFF")
                else:
                    # -------------------------------------------------------
                    # Single item — classify, verify, feedback, publish
                    # -------------------------------------------------------
                    det = detections[0]
                    log.debug("Assigning bin for bbox=%s", det.bbox)
                    detected_bin  = bin_det.assign_bin(det.bbox)
                    volume_liters = estimator.estimate(det.bbox, dist_mm)
                    log.debug("Volume estimate=%.4fL  detected_bin=%s", volume_liters, detected_bin)

                    log.debug("Calling Gemini verifier for item=%s bin=%s", det.label, detected_bin)
                    is_correct, reason = verifier.verify(det.label, detected_bin)
                    log.debug("Verifier result: correct=%s  reason=%s", is_correct, reason)

                    log.info(
                        "item=%s  category=%s  conf=%.2f  bin=%s  correct=%s  vol=%.3fL  dist=%dmm",
                        det.label, det.category, det.confidence,
                        detected_bin, is_correct, volume_liters, dist_mm,
                    )

                    color = (0, 200, 0) if is_correct else (0, 0, 220)
                    x, y, w, h = det.bbox
                    cv2.rectangle(display, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(
                        display,
                        f"{det.label} ({detected_bin}) {'OK' if is_correct else 'WRONG'}",
                        (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1,
                    )

                    cmd = "LED:GREEN" if is_correct else "LED:RED"
                    log.debug("Sending %s", cmd)
                    if is_correct:
                        serial.send_command("LED:GREEN")
                    else:
                        serial.send_command("LED:RED")
                        serial.send_command("BUZZ:3")

                    log.debug("Publishing to MQTT topic=%s", Config.MQTT_TOPIC)
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
                    log.debug("Publish done — waiting 2s before clearing LED")

                    time.sleep(2.0)
                    serial.send_command("LED:OFF")

            dist_label = f"dist: {int(dist_mm)}mm" if dist_mm is not None else "dist: --"
            cv2.putText(display, dist_label, (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
            cv2.imshow("CarbinWatcher", display)
            if cv2.waitKey(1) == ord("q"):
                break

    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        serial.close()
        publisher.disconnect()


if __name__ == "__main__":
    run()
