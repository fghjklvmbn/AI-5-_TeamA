from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from ..database import Database


MEMORY_TYPES = {"preference", "profile", "fact", "schedule", "relationship"}
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
SENSITIVE_RE = re.compile(
    r"(?:비밀번호|패스워드|주민(?:등록)?번호|계좌번호|카드번호|보안코드|인증번호|"
    r"api\s*key|access\s*token|secret\s*key)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_type: str
    content: str
    confidence: float = 0.75
    importance: float = 0.6


class MemoryEngine:
    """Small, local long-term memory layer with deterministic retrieval.

    Memories are isolated by authenticated user ID. Retrieval combines token
    overlap, importance, confidence, and recency so it works without a separate
    embedding server. Qwen can add structured candidates, while the rules below
    keep essential Korean memory phrases functional when the model is offline.
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".!?。")

    @staticmethod
    def keywords(text: str) -> list[str]:
        return list(dict.fromkeys(TOKEN_RE.findall(text.lower())))

    def remember(
        self,
        user_id: str,
        session_id: str | None,
        candidate: MemoryCandidate,
    ):
        memory_type = candidate.memory_type if candidate.memory_type in MEMORY_TYPES else "fact"
        content = re.sub(r"\s+", " ", candidate.content.strip())[:1000]
        if len(content) < 2 or SENSITIVE_RE.search(content):
            return None
        return self.db.upsert_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            normalized_content=self.normalize(content),
            keywords=" ".join(self.keywords(content)),
            confidence=max(0.0, min(1.0, candidate.confidence)),
            importance=max(0.0, min(1.0, candidate.importance)),
        )

    def remember_many(
        self,
        user_id: str,
        session_id: str | None,
        candidates: Iterable[MemoryCandidate],
    ) -> list:
        result = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self.normalize(candidate.content)
            if normalized in seen:
                continue
            seen.add(normalized)
            memory = self.remember(user_id, session_id, candidate)
            if memory is not None:
                result.append(memory)
        return result

    def extract_rule_candidates(self, text: str) -> list[MemoryCandidate]:
        clean = re.sub(r"\s+", " ", text.strip())
        result: list[MemoryCandidate] = []

        explicit = re.search(r"(?:기억해\s?줘|기억해\s?주세요|잊지\s?마)[:：]?\s*(.+)", clean)
        if explicit:
            result.append(MemoryCandidate("fact", explicit.group(1), 0.96, 0.9))

        profile_patterns = (
            r"(?:내|제)\s*이름은\s+([^,.!?]+)",
            r"(?:나는|저는)\s+([^,.!?]+?)(?:이야|예요|입니다)(?:[,.!?]|$)",
        )
        for pattern in profile_patterns:
            match = re.search(pattern, clean)
            if match:
                result.append(MemoryCandidate("profile", match.group(0).strip(), 0.9, 0.82))

        if re.search(r"(?:좋아해|좋아합니다|싫어해|싫어합니다|선호해|선호합니다)", clean):
            result.append(MemoryCandidate("preference", clean, 0.86, 0.72))

        if re.search(r"(?:오늘|내일|모레|다음\s?주|\d{1,2}월|\d{1,2}일|오전|오후).*(?:일정|약속|회의|병원|예약|만나)", clean):
            result.append(MemoryCandidate("schedule", clean, 0.84, 0.88))

        if re.search(r"(?:엄마|아빠|어머니|아버지|남편|아내|아들|딸|친구|동료).*(?:은|는|이|가)", clean):
            result.append(MemoryCandidate("relationship", clean, 0.76, 0.68))

        return result[:5]

    def retrieve(self, user_id: str, query: str, limit: int = 6) -> list:
        rows = self.db.list_memories(user_id, limit=500)
        if not rows:
            return []
        query_tokens = set(self.keywords(query))
        now = datetime.now(UTC)

        def score(row) -> float:
            memory_tokens = set((row["keywords"] or "").split())
            overlap = len(query_tokens & memory_tokens) / max(1, len(query_tokens))
            updated = datetime.fromisoformat(row["updated_at"])
            age_days = max(0.0, (now - updated).total_seconds() / 86400)
            recency = math.exp(-age_days / 90)
            return (
                overlap * 0.58
                + float(row["importance"]) * 0.2
                + float(row["confidence"]) * 0.12
                + recency * 0.1
            )

        ranked = sorted(rows, key=score, reverse=True)
        selected = ranked[:limit]
        self.db.touch_memories(user_id, [row["id"] for row in selected])
        return selected

    @staticmethod
    def as_prompt(memories: list) -> str:
        if not memories:
            return "저장된 관련 기억 없음"
        labels = {
            "preference": "취향",
            "profile": "프로필",
            "fact": "사실",
            "schedule": "일정",
            "relationship": "관계",
        }
        return "\n".join(
            f"- [{labels.get(row['memory_type'], '기억')}] {row['content']}" for row in memories
        )
