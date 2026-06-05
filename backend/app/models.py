"""Pydantic models for the roast engine and the API.

Template models mirror roast-library/schema.json. API models are the request/
response shapes for FastAPI.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ----- Library enums -----

class RoastMode(str, Enum):
    FRIENDLY    = "friendly"
    SAVAGE      = "savage"
    PROGRAMMER  = "programmer"
    STUDENT     = "student"
    GAMER       = "gamer"
    CORPORATE   = "corporate"
    STARTUP     = "startup"
    GENERAL     = "general"


class Personality(str, Enum):
    SAVAGE_ONE        = "savage_one"
    SARCASTIC_FRIEND  = "sarcastic_friend"
    TOXIC_INTERVIEWER = "toxic_interviewer"
    STARTUP_INVESTOR  = "startup_investor"
    PROFESSOR         = "professor"
    GAMER             = "gamer"


class Tone(str, Enum):
    LIGHT    = "light"
    PLAYFUL  = "playful"
    DRY      = "dry"
    CUTTING  = "cutting"
    BRUTAL   = "brutal"


PlaceholderType = Literal["enum", "context", "intent", "history", "username", "roaster"]


class PlaceholderSpec(BaseModel):
    """When a placeholder is an object in the JSON."""
    model_config = ConfigDict(extra="ignore")

    type: PlaceholderType
    values: Optional[list[str]] = None
    default: Optional[str] = None
    # 'key' is used by the filler for `history` type to look up a specific
    # session value (e.g. "last_session_damage_pct"). Allowed but optional.
    key: Optional[str] = None


# A placeholder value is either a plain list of strings (shorthand for
# {type: "enum", values: [...]}) or a full PlaceholderSpec.
PlaceholderValue = Union[list[str], PlaceholderSpec]


def normalize_placeholder(raw: Any) -> PlaceholderSpec:
    """Coerce JSON list-or-object into a PlaceholderSpec."""
    if isinstance(raw, list):
        if not raw:
            raise ValueError("placeholder list must have at least one value")
        return PlaceholderSpec(type="enum", values=list(raw))
    if isinstance(raw, dict):
        return PlaceholderSpec.model_validate(raw)
    raise ValueError(f"invalid placeholder spec: {raw!r}")


class RoastTemplate(BaseModel):
    """A single roast template. Mirrors schema.json."""
    model_config = ConfigDict(extra="ignore")

    id: str
    mode: RoastMode
    subcategory: Optional[str] = None
    personalities: list[Personality] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    trigger_phrases: list[str] = Field(default_factory=list)
    damage: int = Field(ge=1, le=10)
    tone: Tone
    context_tags: list[str] = Field(default_factory=list)
    template: str = Field(min_length=1)
    placeholders: dict[str, Any] = Field(default_factory=dict)
    reaction: Optional[str] = None
    followup_id: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("personalities")
    @classmethod
    def _no_empty_for_blocking_personalities(cls, v):
        # An empty personalities list means "any personality may deliver this".
        return v


class SpecialTemplate(BaseModel):
    """Used for openers / closers / comebacks / callbacks."""
    model_config = ConfigDict(extra="ignore")

    id: str
    mode: Optional[RoastMode] = None
    personalities: list[Personality] = Field(default_factory=list)
    template: str
    placeholders: dict[str, Any] = Field(default_factory=dict)
    reaction: Optional[str] = None
    damage: Optional[int] = None
    tone: Optional[Tone] = None


class PersonalityDef(BaseModel):
    label: str
    description: str
    tone: Tone
    min_damage: int
    max_damage: int
    allowed_modes: list[RoastMode]
    blocked_modes: list[RoastMode] = Field(default_factory=list)
    prefixes: list[str] = Field(default_factory=list)
    suffixes: list[str] = Field(default_factory=list)
    signature_intro: str
    signature_outro: str


class PersonalitiesFile(BaseModel):
    version: int
    default_personality: str
    personalities: dict[str, PersonalityDef]


class IntentDef(BaseModel):
    label: str
    weight: float = 1.0
    keywords: list[str] = Field(default_factory=list)
    phrases: list[str] = Field(default_factory=list)
    # Per-intent keyword-score threshold. A keyword-only hit must reach this
    # score before the intent is considered detected (phrase matches are added
    # on top with their normal weight and are not affected by this number).
    # Defaults to None, which means "use the global scoring.min_score_threshold".
    min_keyword_score: Optional[int] = None


class IntentScoring(BaseModel):
    exact_phrase_match: int = 10
    keyword_match: int = 1
    decay_per_position: int = 0
    min_score_threshold: int = 1


class IntentsFile(BaseModel):
    version: int
    fallback_intent: str
    scoring: IntentScoring
    intents: dict[str, IntentDef]


# ----- Session / API models -----

class SessionScores(BaseModel):
    confidence_lost: int = 0
    emotional_damage: int = 0
    delusion_level: str = "Mildly Aware"
    questionable_decisions: int = 0
    reality_checks: int = 0
    excuses_used: int = 0
    recovery_time: str = "15 minutes and a snack"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    intents: list[str] = Field(default_factory=list)


class Session(BaseModel):
    session_id: str
    username: Optional[str] = None
    # Owning user id (set on start if the caller is authenticated). Used
    # by /session/{id}/end and /session/{id} to refuse cross-user access:
    # an anonymous caller can't take over an authed user's session, and
    # an authed user can't end or read another user's session. None for
    # anonymous sessions, which are intentionally public.
    user_id: Optional[int] = None
    # Which gender of roaster the user picked (male/female/neutral). Drives
    # roaster selection and pronoun usage in personalized roast generation.
    roaster_gender: Optional[str] = Field(default=None, pattern="^(male|female|neutral)$")
    mode: RoastMode
    personality: Personality
    created_at: float
    message_count: int = 0
    total_damage: int = 0
    comeback_attempts: int = 0
    comeback_failures: int = 0
    scores: SessionScores = Field(default_factory=SessionScores)
    history: list[ChatMessage] = Field(default_factory=list)
    recent_roast_ids: list[str] = Field(default_factory=list)
    detected_intents: list[str] = Field(default_factory=list)
    opener_used: bool = False
    closer_used: bool = False
    # Set when the user calls /end. Sessions are kept around (read-only) so the
    # share URL can still load the conversation. The /roast endpoint returns
    # 410 Gone if a message is sent to an ended session.
    ended_at: Optional[float] = None
    # The closer that was delivered to the user on /end. Persisted so the
    # share page can show the final line, and so retrying /end (idempotent)
    # returns the same closer instead of rolling a new one.
    closer_text: Optional[str] = None


# ----- API request/response -----

class StartSessionRequest(BaseModel):
    mode: RoastMode
    personality: Personality
    username: Optional[str] = Field(default=None, min_length=1, max_length=64)
    roaster_gender: Optional[str] = Field(default=None, pattern="^(male|female|neutral)$")

    @field_validator("username")
    @classmethod
    def _strip_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None  # treat empty/whitespace as anonymous
        return v


class StartSessionResponse(BaseModel):
    session_id: str
    opener: str
    scores: SessionScores
    mode: RoastMode
    personality: Personality
    roaster_gender: Optional[str] = None


class RoastRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def _no_blank_messages(cls, v: str) -> str:
        # Pydantic's min_length=1 accepts "   ". Reject anything that is
        # whitespace-only, so the engine doesn't waste a recent-roast slot.
        if not v.strip():
            raise ValueError("message cannot be blank or whitespace-only")
        return v


class RoastResponse(BaseModel):
    roast: str
    scores: SessionScores
    intents_detected: list[str]
    is_opener: bool = False
    is_closer: bool = False
    is_comeback: bool = False
    template_id: Optional[str] = None


class EndSessionResponse(BaseModel):
    session_id: str
    final_scores: SessionScores
    closer: Optional[str] = None
    share_url: Optional[str] = None


class SessionStateResponse(BaseModel):
    session_id: str
    mode: RoastMode
    personality: Personality
    message_count: int
    scores: SessionScores
    history: list[ChatMessage]
    is_ended: bool = False


class ModesResponse(BaseModel):
    modes: list[RoastMode]


class PersonalitiesResponse(BaseModel):
    personalities: list[Personality]
