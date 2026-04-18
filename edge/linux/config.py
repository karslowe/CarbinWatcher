import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Device identity
    USER_ID: str = os.getenv("USER_ID", "u1")
    THING_NAME: str = os.getenv("IOT_THING_NAME", "carbinwatcher-01")

    # Camera
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    FRAME_WIDTH: int = int(os.getenv("FRAME_WIDTH", "640"))
    FRAME_HEIGHT: int = int(os.getenv("FRAME_HEIGHT", "480"))
    # Focal length in pixels — calibrate with a known-size object at a known distance:
    #   focal_length_px = (pixel_width * known_dist_mm) / known_real_width_mm
    FOCAL_LENGTH_PX: float = float(os.getenv("FOCAL_LENGTH_PX", "600.0"))

    # Two-bin layout — which bin occupies the left vs right half of the frame
    BIN_LEFT: str = os.getenv("BIN_LEFT", "recycle")
    BIN_RIGHT: str = os.getenv("BIN_RIGHT", "landfill")

    # Detection trigger
    TRIGGER_DIST_MM: float = float(os.getenv("TRIGGER_DIST_MM", "400.0"))
    STABILIZE_MS: int = int(os.getenv("STABILIZE_MS", "500"))
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))
    COOLDOWN_S: float = float(os.getenv("COOLDOWN_S", "3.0"))

    # ONNX model
    MODEL_PATH: str = os.getenv("MODEL_PATH", "models/trash_detector.onnx")
    LABELS_PATH: str = os.getenv("LABELS_PATH", "models/labels.txt")

    # Serial / MCU
    SERIAL_PORT: str = os.getenv("SERIAL_PORT", "/dev/ttyACM0")
    SERIAL_BAUD: int = int(os.getenv("SERIAL_BAUD", "115200"))

    # AWS S3
    S3_BUCKET: str = os.getenv("S3_BUCKET", "carbinwatcher-raw")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
