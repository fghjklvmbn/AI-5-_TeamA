from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from ..database import Database

# 앗.. 정규표현식 너무 쓴것 같은데 정당해서 변경할수가 없다..
MEMORY_TYPES = {"preference", "profile", "fact", "schedule", "relationship"}
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
RECALL_RE = re.compile(
    r"(?:기억(?:이|을|나|해)?|가물가물|뭐였(?:지|죠)|뭐더라|생각(?:이)?\s*안\s*나|"
    r"잊어버|전에\s*말한|내가\s*말했|제가\s*말했|알려줬)", re.IGNORECASE,
)
QUESTION_RE = re.compile(r"(?:[?？]|뭐|무엇|어떤|언제|어디|누구|알려|추천|기억)", re.IGNORECASE)
STOPWORDS = {
    "내가", "제가", "나는", "저는", "우리", "그거", "그게", "이거", "이게",
    "무엇", "뭐가", "어떤", "대해서", "관련", "질문", "알려줘", "알려주세요",
    "오늘", "내일", "모레", "이번", "저번", "정말", "그냥", "혹시",
}

# 타입 힌트(구분을 위함)
TYPE_HINTS = {
    "preference": re.compile(r"(?:좋아|싫어|취향|선호|즐겨)"),
    "profile": re.compile(r"(?:이름|직업|나이|생일|사는\s*곳|고향)"),
    "schedule": re.compile(r"(?:일정|약속|예약|언제|날짜|회의|병원|치과)"),
    "relationship": re.compile(r"(?:가족|엄마|아빠|어머니|아버지|남편|아내|아들|딸|친구|동료)"),
}

# Long-term memory is deliberately conservative. Labels alone are insufficient:
# users and model-generated candidates can contain raw credentials or identifiers.
SENSITIVE_LABEL_RE = re.compile(
    r"(?:비밀번호|패스워드|주민(?:등록)?번호|계좌번호|카드번호|보안코드|인증번호|"
    r"api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|secret[\s_-]*key|"
    r"client[\s_-]*secret|private[\s_-]*key|password|passcode|authorization\s*:\s*bearer)",
    re.IGNORECASE,
)
RESIDENT_REGISTRATION_RE = re.compile(
    r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
    r"[-\s\u2010-\u2015]?[1-8]\d{6}(?!\d)"
)
PHONE_RE = re.compile(
    r"(?<!\d)(?:"
    r"(?:\+82[-.\s]?)?0?1[016789][-.\s]?\d{3,4}[-.\s]?\d{4}|"
    r"0(?:2|[3-6]\d)[-.\s]?\d{3,4}[-.\s]?\d{4}"
    r")(?!\d)"
)
PHONE_CANDIDATE_RE = re.compile(
    r"(?<!\d)(\+?(?:\d[-().\s]*){8,12}\d)(?!\d)"
)
EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\."
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+(?![\w.-])",
    re.IGNORECASE,
)
JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
API_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"sk-(?:live|test|proj)-[A-Za-z0-9_-]{16,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{20,}|"
    r"AKIA[A-Z0-9]{16}"
    r")(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
CARD_NUMBER_RE = re.compile(r"(?<!\d)(?:\d[-.\s]?){12,18}\d(?!\d)")
SECRET_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z0-9_+/=-]{24,})(?![A-Za-z0-9])"
)
GROUPED_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9])((?:[A-Za-z0-9]{4}[-\s]){5,}[A-Za-z0-9]{4})(?![A-Za-z0-9])"
)


def _passes_luhn(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _looks_like_korean_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if value.lstrip().startswith("+82") or digits.startswith("82"):
        digits = "0" + digits[2:]
    if len(digits) in {10, 11} and re.match(r"^01[016789]", digits):
        return True
    if len(digits) in {9, 10} and digits.startswith("02"):
        return True
    return len(digits) in {10, 11} and re.match(r"^0[3-6]\d", digits) is not None


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    return -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in (value.count(character) for character in set(value))
    )


def _looks_like_high_entropy_secret(value: str) -> bool:
    token = value.rstrip("=")
    if len(token) < 24:
        return False
    character_classes = sum((
        any(character.islower() for character in token),
        any(character.isupper() for character in token),
        any(character.isdigit() for character in token),
        any(character in "_+/-" for character in token),
    ))
    if character_classes < 2:
        return False
    entropy = _shannon_entropy(token)
    if len(token) >= 32 and re.fullmatch(r"[0-9a-fA-F]+", token):
        return entropy >= 3.35
    return entropy >= 4.0


def contains_sensitive_information(text: str) -> bool:
    """Detect raw personal identifiers and credentials before durable storage."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", value)
    if any(pattern.search(value) for pattern in (
        SENSITIVE_LABEL_RE,
        RESIDENT_REGISTRATION_RE,
        PHONE_RE,
        EMAIL_RE,
        JWT_RE,
        API_TOKEN_RE,
    )):
        return True
    if any(
        _looks_like_korean_phone(match.group(1))
        for match in PHONE_CANDIDATE_RE.finditer(value)
    ):
        return True
    if any(_passes_luhn(match.group(0)) for match in CARD_NUMBER_RE.finditer(value)):
        return True
    if any(
        _looks_like_high_entropy_secret(match.group(1))
        for match in SECRET_CANDIDATE_RE.finditer(value)
    ):
        return True
    return any(
        _looks_like_high_entropy_secret(re.sub(r"[-\s]", "", match.group(1)))
        for match in GROUPED_SECRET_RE.finditer(value)
    )


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_type: str
    content: str
    confidence: float = 0.75
    importance: float = 0.6

# 메모리 엔진(챗봇에서 값을 빼내고, 저장하도록 도와주는 주체)
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
        expected_auth_version: int | None = None,
    ):
        memory_type = candidate.memory_type if candidate.memory_type in MEMORY_TYPES else "fact"
        raw_content = re.sub(r"\s+", " ", candidate.content.strip())
        if len(raw_content) < 2 or contains_sensitive_information(raw_content):
            return None
        content = raw_content[:1000]
        return self.db.upsert_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            normalized_content=self.normalize(content),
            keywords=" ".join(self.keywords(content)),
            confidence=max(0.0, min(1.0, candidate.confidence)),
            importance=max(0.0, min(1.0, candidate.importance)),
            expected_auth_version=expected_auth_version,
        )

    def remember_many(
        self,
        user_id: str,
        session_id: str | None,
        candidates: Iterable[MemoryCandidate],
        expected_auth_version: int | None = None,
    ) -> list:
        result = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self.normalize(candidate.content)
            if normalized in seen:
                continue
            seen.add(normalized)
            memory = self.remember(
                user_id, session_id, candidate,
                expected_auth_version=expected_auth_version,
            )
            if memory is not None:
                result.append(memory)
        return result

    # 메모리 엔진 발동 조건 추출
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

    # 메모리 엔진 중심, 기억해야 할 것을 파악하고 점수로 매겨 기억 가중치 측정
    def retrieve(self, user_id: str, query: str, limit: int = 6) -> list:
        rows = self.db.list_memories(user_id, limit=500)
        if not rows:
            return []
        query_tokens = {token for token in self.keywords(query) if token not in STOPWORDS}
        recall_requested = bool(RECALL_RE.search(query))
        question_requested = bool(QUESTION_RE.search(query))
        hinted_types = {kind for kind, pattern in TYPE_HINTS.items() if pattern.search(query)}
        now = datetime.now(UTC)

        def token_matches(memory_tokens: set[str]) -> int:
            return sum(
                1 for query_token in query_tokens
                if any(
                    query_token == memory_token
                    or (min(len(query_token), len(memory_token)) >= 3 and (
                        query_token.startswith(memory_token) or memory_token.startswith(query_token)
                    ))
                    for memory_token in memory_tokens
                )
            )

        def relevance(row) -> tuple[bool, float]:
            memory_tokens = set((row["keywords"] or "").split())
            matches = token_matches(memory_tokens)
            overlap = matches / max(1, len(query_tokens))
            type_match = row["memory_type"] in hinted_types
            generic_recall = recall_requested and not hinted_types and len(query_tokens) <= 2
            eligible = matches > 0 or ((recall_requested or question_requested) and type_match) or generic_recall
            return eligible, overlap + (0.35 if type_match else 0.0)

        def score(row, relevance_score: float) -> float:
            updated = datetime.fromisoformat(row["updated_at"])
            age_days = max(0.0, (now - updated).total_seconds() / 86400)
            recency = math.exp(-age_days / 90)
            return (
                relevance_score * 0.82
                + float(row["importance"]) * 0.08
                + float(row["confidence"]) * 0.06
                + recency * 0.04
            )

        eligible_rows = []
        for row in rows:
            eligible, relevance_score = relevance(row)
            if eligible:
                eligible_rows.append((score(row, relevance_score), row))
        eligible_rows.sort(key=lambda item: item[0], reverse=True)
        effective_limit = min(limit, 2) if recall_requested and not hinted_types else min(limit, 3)
        selected = [row for _, row in eligible_rows[:effective_limit]]
        self.db.touch_memories(user_id, [row["id"] for row in selected])
        return selected

    @staticmethod
    def as_prompt(memories: list) -> str:
        if not memories:
            return ""
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
