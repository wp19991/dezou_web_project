from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateSessionRequest(BaseModel):
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    seat_count: int = Field(ge=2, le=9)
    small_blind: int = Field(ge=1)
    big_blind: int = Field(ge=2)
    starting_stack: int = Field(ge=1)
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    seat_names: list[str] | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_business_rules(self) -> "CreateSessionRequest":
        if self.big_blind <= self.small_blind:
            raise ValueError("big_blind must be greater than small_blind")
        if self.starting_stack < self.big_blind * 20:
            raise ValueError("starting_stack must be at least big_blind * 20")
        if self.seat_names is not None and len(self.seat_names) != self.seat_count:
            raise ValueError("seat_names length must equal seat_count")
        return self

    @field_validator("seat_names")
    @classmethod
    def validate_seat_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = [item.strip() for item in value]
        for item in normalized:
            if not (1 <= len(item) <= 32):
                raise ValueError("seat name length must be between 1 and 32")
        if len(set(normalized)) != len(normalized):
            raise ValueError("seat names must be unique")
        return normalized


class StartHandRequest(BaseModel):
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    dealer_seat: int | None = Field(default=None, ge=0, le=8)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class SubmitActionRequest(BaseModel):
    actor_id: str | None = Field(default=None, pattern=r"^seat_[0-8]$")
    actor_name: str | None = Field(default=None, min_length=1, max_length=32)
    action: str
    amount: int | None = Field(default=None, ge=0)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_actor_identity(self) -> "SubmitActionRequest":
        if not self.actor_id and not self.actor_name:
            raise ValueError("actor_id or actor_name is required")
        return self

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        allowed = {"fold", "check", "call", "bet", "raise", "all_in"}
        if value not in allowed:
            raise ValueError("unsupported action")
        return value


class SendChatRequest(BaseModel):
    speaker_id: str | None = Field(default=None, pattern=r"^seat_[0-8]$")
    speaker_name: str | None = Field(default=None, min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=200)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_speaker_identity(self) -> "SendChatRequest":
        if not self.speaker_id and not self.speaker_name:
            raise ValueError("speaker_id or speaker_name is required")
        return self
