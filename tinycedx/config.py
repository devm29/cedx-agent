from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SEED_DIR = Path(os.environ.get("SEED_DIR", str(REPO_ROOT / "seed")))
OUT_DIR = Path(os.environ.get("OUT_DIR", str(REPO_ROOT / "out")))
TRANSCRIPTS_DIR = Path(os.environ.get("TRANSCRIPTS_DIR", str(REPO_ROOT / "transcripts")))

REPLAY_LLM = os.environ.get("REPLAY_LLM", "true").strip().lower() in {"1", "true", "yes"}
CASE_ID = os.environ.get("CASE_ID", "CEDX-82C0A1")
PIPELINE_NOW = os.environ.get("PIPELINE_NOW", "2026-06-26")
PIPELINE_VERSION = "tinycedx-lawfirms-v1"

LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL") or None
LLM_MODEL_STRONG = os.environ.get("LLM_MODEL_STRONG") or None
LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or None

MAX_COST_USD_PER_RECORD = float(os.environ.get("MAX_COST_USD_PER_RECORD", "0.02"))
MAX_STEPS_PER_RECORD = int(os.environ.get("MAX_STEPS_PER_RECORD", "4"))

MODEL_PRICING_PER_1K = {
    "cheap": {"model": "gpt-4o-mini", "in": 0.00015, "out": 0.00060},
    "strong": {"model": "gpt-4o", "in": 0.00250, "out": 0.01000},
}

ESTIMATED_TOKENS_IN = 200
ESTIMATED_TOKENS_OUT = 100


def live_model_for(tier: str) -> str:
    """Model to call on the live path. LLM_MODEL replaces the cheap tier (and the strong tier
    too, unless LLM_MODEL_STRONG is set); with neither set the router's defaults are used."""
    if tier == "strong":
        return LLM_MODEL_STRONG or LLM_MODEL or MODEL_PRICING_PER_1K["strong"]["model"]
    return LLM_MODEL or MODEL_PRICING_PER_1K["cheap"]["model"]


def estimate_cost(tier: str) -> float:
    pricing = MODEL_PRICING_PER_1K[tier]
    return (ESTIMATED_TOKENS_IN / 1000) * pricing["in"] + (ESTIMATED_TOKENS_OUT / 1000) * pricing["out"]


OUTLIER_MODIFIED_Z_THRESHOLD = 3.5
LOW_CONFIDENCE_THRESHOLD = 0.55

REQUIRED_FIELDS = ("id", "owner", "deadline", "category", "amount")
KNOWN_CATEGORIES = {"ONBOARDING", "RENEWAL", "REVIEW", "REPORT", "INTAKE"}
