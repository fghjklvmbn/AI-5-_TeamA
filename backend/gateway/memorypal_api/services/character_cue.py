from __future__ import annotations

import json
import re
from typing import Any


_EXCITED = re.compile(r"(축하|대단|멋지|좋아|기쁘|신나|성공|와[!！])", re.IGNORECASE)
_HAPPY = re.compile(r"(고마|반가|다행|행복|웃|좋은|좋아요)", re.IGNORECASE)
_SAD = re.compile(r"(슬프|외롭|눈물|상실|힘들었|아프겠)", re.IGNORECASE)
_CONCERNED = re.compile(r"(걱정|괜찮|조심|불안|힘들|어렵|속상)", re.IGNORECASE)
_EMOTIONS = {"neutral", "happy", "sad", "concerned", "excited"}
_GESTURES = {"idle", "nod", "comfort", "celebrate"}
_VOICE_STYLES = {"calm", "warm", "bright"}


def character_cue_for(text: str) -> dict[str, Any]:
    """Derive a bounded animation and voice cue from assistant text."""
    normalized = text.strip()
    if _EXCITED.search(normalized):
        emotion, gesture, voice_style = "excited", "celebrate", "bright"
    elif _SAD.search(normalized):
        emotion, gesture, voice_style = "sad", "comfort", "warm"
    elif _CONCERNED.search(normalized):
        emotion, gesture, voice_style = "concerned", "comfort", "calm"
    elif _HAPPY.search(normalized):
        emotion, gesture, voice_style = "happy", "nod", "bright"
    else:
        emotion, gesture, voice_style = "neutral", "idle", "calm"
    emphasis = min(1.0, normalized.count("!") * 0.12 + normalized.count("！") * 0.12)
    intensity = min(1.0, (0.72 if emotion == "excited" else 0.48) + emphasis)
    return {
        "emotion": emotion,
        "intensity": round(intensity, 2),
        "gesture": gesture,
        "voice_style": voice_style,
    }


def parse_character_cue(raw: str | dict[str, Any] | None, fallback_text: str) -> dict[str, Any]:
    """Validate structured model output and fall back to deterministic inference."""
    try:
        if isinstance(raw, dict):
            value = raw
        else:
            match = re.search(r"\{[\s\S]*\}", str(raw or ""))
            value = json.loads(match.group(0) if match else str(raw or ""))
        emotion = str(value.get("emotion") or "")
        gesture = str(value.get("gesture") or "")
        voice_style = str(value.get("voice_style") or "")
        intensity = min(1.0, max(0.0, float(value.get("intensity", 0.5))))
        if emotion not in _EMOTIONS or gesture not in _GESTURES or voice_style not in _VOICE_STYLES:
            raise ValueError("unsupported character cue")
        return {
            "emotion": emotion,
            "intensity": round(intensity, 2),
            "gesture": gesture,
            "voice_style": voice_style,
        }
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return character_cue_for(fallback_text)
