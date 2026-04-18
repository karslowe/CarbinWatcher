"""CarbinWatcher backend — FastAPI + Gemini agent scaffold.

Stubs only. Tool functions return hardcoded shapes so the frontend can start
consuming. Fill in real logic (DynamoDB reads, Gemini tool-calling loop) next.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="CarbinWatcher API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas ----------

class ChatRequest(BaseModel):
    message: str
    user_id: str


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str]


# ---------- Tool stubs ----------
# Each returns a realistic-shaped hardcoded payload. Replace with DynamoDB /
# Databricks queries when those are ready.

def get_user_totals(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "period": "all_time",
        "item_count": 42,
        "totals_by_category": {
            "food_waste": {"items": 18, "weight_kg": 3.4},
            "recycling": {"items": 15, "weight_kg": 2.1},
            "landfill": {"items": 7, "weight_kg": 1.2},
            "compost": {"items": 2, "weight_kg": 0.3},
        },
    }


def calculate_climate_impact(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "co2e_saved_kg": 12.7,
        "equivalents": {
            "miles_not_driven": 31.4,
            "trees_planted": 0.6,
            "phone_charges": 1543,
        },
    }


def get_waste_breakdown_by_category(user_id: str, period: str = "week") -> dict[str, Any]:
    return {
        "user_id": user_id,
        "period": period,
        "breakdown": {
            "food_waste": [
                {"item": "banana peel", "weight_kg": 0.12},
                {"item": "coffee grounds", "weight_kg": 0.25},
            ],
            "recycling": [
                {"item": "aluminum can", "weight_kg": 0.015},
                {"item": "cardboard box", "weight_kg": 0.30},
            ],
            "landfill": [
                {"item": "plastic wrap", "weight_kg": 0.02},
            ],
            "compost": [
                {"item": "eggshells", "weight_kg": 0.08},
            ],
        },
    }


def get_items_at_risk_of_spoiling(user_id: str) -> list[dict[str, Any]]:
    return [
        {"item": "spinach", "days_in_fridge": 6, "spoilage_risk": "high"},
        {"item": "greek yogurt", "days_in_fridge": 10, "spoilage_risk": "medium"},
        {"item": "strawberries", "days_in_fridge": 4, "spoilage_risk": "medium"},
    ]


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_user_totals": get_user_totals,
    "calculate_climate_impact": calculate_climate_impact,
    "get_waste_breakdown_by_category": get_waste_breakdown_by_category,
    "get_items_at_risk_of_spoiling": get_items_at_risk_of_spoiling,
}


# ---------- Routes ----------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # TODO: wire up Gemini tool-calling loop here.
    #   1. Configure google.generativeai with GEMINI_API_KEY
    #   2. Declare tools from TOOL_REGISTRY via function_declarations
    #   3. Call model.generate_content(req.message, tools=...)
    #   4. Loop: resolve any function_call parts through TOOL_REGISTRY and
    #      feed responses back until the model returns a plain text reply.
    return ChatResponse(
        reply=f"[stub] received: {req.message!r} for user {req.user_id}",
        tools_used=[],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
