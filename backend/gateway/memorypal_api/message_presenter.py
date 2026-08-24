from __future__ import annotations

import json
from typing import Any, Mapping

from .schemas import MessageResponse
from .services.character_cue import parse_character_cue


def stored_character_cue(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row["character_cue_json"] if "character_cue_json" in row.keys() else None
    return parse_character_cue(raw, str(row["assistant_text"] or ""))


def serialize_character_cue(cue: dict[str, Any]) -> str:
    return json.dumps(cue, ensure_ascii=False, separators=(",", ":"))


def message_response(row: Mapping[str, Any], *, audio_url: str | None) -> MessageResponse:
    raw_attachments = row["attachment_refs_json"] if "attachment_refs_json" in row.keys() else "[]"
    try:
        parsed_attachments = json.loads(str(raw_attachments or "[]"))
        attachments = parsed_attachments if isinstance(parsed_attachments, list) else []
    except (TypeError, ValueError):
        attachments = []
    return MessageResponse(
        id=row["id"],
        user_text=row["user_text"],
        assistant_text=row["assistant_text"],
        audio_url=audio_url,
        created_at=row["created_at"],
        character_cue=stored_character_cue(row),
        attachments=attachments,
    )
