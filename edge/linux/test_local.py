"""
Local test harness for the CarbinWatcher inferencing loop.

Runs the full real pipeline — Gemini verification and AWS IoT Core publishing
are live. Only the Arduino serial link is stubbed (simulated fixed distance).

Usage:
    # Live webcam (default)
    python test_local.py

    # Static image — press SPACE to run inference, 'q' to quit
    python test_local.py --image path/to/image.jpg

    # Pre-recorded video
    python test_local.py --video path/to/clip.mp4

Controls:
    SPACE  — trigger a detection (simulates the distance-sensor event)
    q      — quit

Stubbed:
    SerialComms  →  SimulatedSerial  (prints LED/BUZZ commands; returns fixed dist)

Real (loaded from .env):
    BinVerifier   — calls Gemini Flash (falls back to rules if GEMINI_API_KEY unset)
    MqttPublisher — publishes to AWS IoT Core over mTLS
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

import cv2

# Fail fast if the headless OpenCV build is installed — imshow is silently
# broken in that build. Run: pip install -r requirements_test.txt
try:
    _test_win = "carbinwatcher_gui_check"
    cv2.namedWindow(_test_win, cv2.WINDOW_NORMAL)
    cv2.destroyWindow(_test_win)
except Exception:
    raise SystemExit(
        "\n[ERROR] cv2.imshow is not available.\n"
        "  You likely have 'opencv-python-headless' installed, which has no GUI support.\n"
        "  Fix: pip install -r requirements_test.txt\n"
        "  (This installs 'opencv-python' which includes the display backend.)\n"
    )

from bin_detector import BinDetector
from bin_verifier import BinVerifier
from config import Config
from model_runner import TrashDetector
from mqtt_publisher import MqttPublisher
from volume_estimator import VolumeEstimator

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("carbinwatcher.test")

SIMULATED_DIST_MM = 250.0  # replaces the hardware distance sensor


# ---------------------------------------------------------------------------
# Serial stub — only hardware component replaced
# ---------------------------------------------------------------------------

class SimulatedSerial:
    def __init__(self, dist_mm: float = SIMULATED_DIST_MM):
        self._dist = dist_mm
        log.info("[SERIAL STUB] SimulatedSerial ready — fixed dist=%.0fmm", dist_mm)

    def latest_distance(self) -> float:
        return self._dist

    def send_command(self, cmd: str) -> None:
        log.info("[SERIAL STUB] → %s", cmd)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _draw_hud(frame: cv2.Mat, dist_mm: float, cooldown_left: float) -> None:
    h, w = frame.shape[:2]
    cv2.line(frame, (w // 2, 0), (w // 2, h), (80, 80, 80), 1)
    cv2.putText(frame, Config.BIN_LEFT,  (8,          h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
    cv2.putText(frame, Config.BIN_RIGHT, (w // 2 + 8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
    cv2.putText(frame, f"dist: {int(dist_mm)}mm", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    cd_color = (0, 200, 0) if cooldown_left <= 0 else (0, 100, 220)
    cd_text  = "READY — press SPACE" if cooldown_left <= 0 else f"cooldown: {cooldown_left:.1f}s"
    cv2.putText(frame, cd_text, (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cd_color, 1)


def _draw_detection(frame: cv2.Mat, label: str, detected_bin: str, is_correct: bool,
                    bbox: tuple[int, int, int, int]) -> None:
    color = (0, 200, 0) if is_correct else (0, 0, 220)
    x, y, w, h = bbox
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    verdict = "OK" if is_correct else "WRONG BIN"
    cv2.putText(
        frame,
        f"{label} → {detected_bin} [{verdict}]",
        (x, max(y - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(source: int | str = Config.CAMERA_INDEX) -> None:
    log.info("Loading model: %s", Config.MODEL_PATH)
    detector  = TrashDetector(Config.MODEL_PATH, Config.LABELS_PATH, Config.CONFIDENCE_THRESHOLD)
    bin_det   = BinDetector(Config.FRAME_WIDTH, Config.BIN_LEFT, Config.BIN_RIGHT)
    estimator = VolumeEstimator(Config.FOCAL_LENGTH_PX)

    log.info("Initializing BinVerifier (Gemini model=%s)", Config.GEMINI_MODEL)
    verifier  = BinVerifier(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)

    log.info("Connecting to AWS IoT endpoint=%s topic=%s", Config.IOT_ENDPOINT, Config.MQTT_TOPIC)
    publisher = MqttPublisher(
        iot_endpoint=Config.IOT_ENDPOINT,
        thing_name=Config.THING_NAME,
        cert_path=Config.IOT_CERT_PATH,
        key_path=Config.IOT_KEY_PATH,
        root_ca_path=Config.IOT_ROOT_CA_PATH,
        topic=Config.MQTT_TOPIC,
    )
    publisher.connect()

    serial = SimulatedSerial(SIMULATED_DIST_MM)

    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  Config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open source: {source!r}")

    log.info(
        "CarbinWatcher LOCAL TEST running | bins: LEFT=%s RIGHT=%s | press SPACE to trigger",
        Config.BIN_LEFT, Config.BIN_RIGHT,
    )

    last_detection = -Config.COOLDOWN_S
    last_frame: cv2.Mat | None = None

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                if last_frame is not None:
                    frame = last_frame.copy()
                else:
                    log.warning("Camera read failed — retrying")
                    time.sleep(0.05)
                    continue
            last_frame = frame.copy()

            display = frame.copy()
            dist_mm = serial.latest_distance()
            now     = time.monotonic()
            cooldown_left = max(0.0, Config.COOLDOWN_S - (now - last_detection))

            _draw_hud(display, dist_mm, cooldown_left)
            cv2.imshow("CarbinWatcher [LOCAL TEST]", display)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break

            if key == ord(" ") and cooldown_left <= 0:
                last_detection = now
                log.info("Manual trigger fired — running inference")
                detections = detector.detect(frame)
                log.info("%d detection(s)", len(detections))

                display = frame.copy()
                _draw_hud(display, dist_mm, 0.0)

                if not detections:
                    log.info("No item detected in frame")
                    serial.send_command("LED:OFF")

                elif len(detections) > 1:
                    labels = [d.label for d in detections]
                    log.info("Multiple items: %s — signaling SPLIT", labels)
                    for d in detections:
                        x, y, w, h = d.bbox
                        cv2.rectangle(display, (x, y), (x + w, y + h), (0, 165, 255), 2)
                        cv2.putText(display, d.label, (x, max(y - 6, 12)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 1)
                    serial.send_command("LED:SPLIT")
                    serial.send_command("BUZZ:2")

                else:
                    det = detections[0]
                    detected_bin  = bin_det.assign_bin(det.bbox)
                    volume_liters = estimator.estimate(det.bbox, dist_mm)

                    log.info("Calling Gemini verifier for item=%s bin=%s", det.label, detected_bin)
                    is_correct, reason = verifier.verify(det.label, detected_bin)
                    print(f"\n[Gemini] correct={is_correct}  reason: {reason}\n")

                    log.info(
                        "item=%-20s  category=%-10s  conf=%.2f  bin=%-10s  correct=%s  vol=%.3fL",
                        det.label, det.category, det.confidence,
                        detected_bin, is_correct, volume_liters,
                    )

                    _draw_detection(display, det.label, detected_bin, is_correct, det.bbox)

                    serial.send_command("LED:GREEN" if is_correct else "LED:RED")
                    if not is_correct:
                        serial.send_command("BUZZ:3")

                    publisher.publish({
                        "ts":                datetime.now(timezone.utc).isoformat(),
                        "user_id":           Config.USER_ID,
                        "thing_name":        Config.THING_NAME,
                        "item":              det.label,
                        "category":          det.category,
                        "confidence":        round(det.confidence, 4),
                        "volume_liters_est": round(volume_liters, 4),
                        "dist_mm":           int(dist_mm),
                        "detected_bin":      detected_bin,
                        "placement_correct": is_correct,
                        "reason":            reason,
                    })

                cv2.imshow("CarbinWatcher [LOCAL TEST]", display)
                cv2.waitKey(2000)
                serial.send_command("LED:OFF")

    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        serial.close()
        publisher.disconnect()


# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CarbinWatcher local inference test")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--image",  metavar="PATH", help="static image file")
    src.add_argument("--video",  metavar="PATH", help="pre-recorded video file")
    src.add_argument("--camera", metavar="IDX",  type=int, default=Config.CAMERA_INDEX,
                     help=f"webcam index (default: CAMERA_INDEX from .env, currently {Config.CAMERA_INDEX})")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.image:
        source: int | str = args.image
    elif args.video:
        source = args.video
    else:
        source = args.camera
    run(source)
