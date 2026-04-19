"""
Verifies whether a classified item belongs in the bin it was placed in.

Primary path: Gemini Flash returns {"correct": true|false, "reason": "..."}.
Fallback:     rule-based lookup table used when the API is unavailable.
"""
from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a waste-sorting assistant. "
    "Respond ONLY with a JSON object — no markdown, no extra text: "
    '{"correct": true|false, "reason": "<one sentence>"}'
)

# ---------------------------------------------------------------------------
# Static rule table (used as offline fallback)
# ---------------------------------------------------------------------------
_RECYCLE = {
    "plastic_bottle", "glass_bottle", "metal_can", "cardboard",
    "paper", "newspaper", "aluminum_foil", "beverage_carton",
}
_COMPOST = {"food_waste", "fruit_peel", "coffee_grounds", "eggshell"}
_HAZARDOUS = {"battery", "electronics"}
# Everything else → landfill


def _rule_correct(label: str, bin_type: str) -> tuple[bool, str]:
    if label in _RECYCLE:
        correct = bin_type == "recycle"
    elif label in _COMPOST:
        correct = bin_type == "compost"
    elif label in _HAZARDOUS:
        correct = False  # never correct in standard bins
    else:
        correct = bin_type == "landfill"
    return correct, "rule-based fallback"


# ---------------------------------------------------------------------------

class BinVerifier:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self._model_name = model
        self._config = types.GenerateContentConfig(system_instruction=_SYSTEM)
        if api_key:
            self._client = genai.Client(api_key=api_key)
        else:
            self._client = None
            log.warning("GEMINI_API_KEY not set — using rule-based bin verification only")

    def verify(self, item_label: str, bin_type: str) -> tuple[bool, str]:
        """Return (placement_is_correct, reason_string)."""
        if self._client is None:
            return _rule_correct(item_label, bin_type)

        prompt = (
            f'Item: "{item_label}". '
            f'The user placed it in the "{bin_type}" bin. '
            "Is this correct?"
        )
        try:
            resp = self._client.models.generate_content(
                model=self._model_name, config=self._config, contents=prompt
            )
            text = resp.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(text)
            return bool(data.get("correct", False)), str(data.get("reason", ""))
        except Exception as exc:
            log.warning("Gemini verification failed (%s) — falling back to rules", exc)
            return _rule_correct(item_label, bin_type)
