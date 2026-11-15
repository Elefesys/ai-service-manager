"""Closed pixel-observation result. Provenance and authority are server supplied."""

import unicodedata
from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, field_validator

from asm.ai.contracts import DTO

VISION_PROFILE: Literal["polza_openai_gpt4omini_pixels_v1"] = "polza_openai_gpt4omini_pixels_v1"
PREPROCESS_PROFILE: Literal["exif_contain_white_rgb_png256_strip_v1"] = (
    "exif_contain_white_rgb_png256_strip_v1"
)
VISION_MODEL = "openai/gpt-4o-mini"
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def observation_text(value: str, maximum: int) -> str:
    if (
        not value.strip()
        or len(value.encode("utf-8")) > maximum
        or any(unicodedata.category(c).startswith("C") and c not in "\t\n" for c in value)
    ):
        raise ValueError("INVALID_OBSERVATION")
    return value


class VisionResult(DTO):
    revision: Literal["vision_result_v1"]
    subject: str = Field(min_length=1, max_length=160, repr=False)
    styles: tuple[str, ...] = Field(max_length=4, repr=False)
    details: tuple[str, ...] = Field(max_length=6, repr=False)
    uncertainty: tuple[str, ...] = Field(min_length=1, max_length=4, repr=False)
    scale: Literal["UNKNOWN"]

    @field_validator("subject")
    @classmethod
    def subject_bytes(cls, value: str) -> str:
        return observation_text(value, 160)

    @field_validator("styles", "details", "uncertainty")
    @classmethod
    def list_bytes(cls, values: tuple[str, ...], info: ValidationInfo) -> tuple[str, ...]:
        maximum = 40 if info.field_name == "styles" else 120
        for value in values:
            observation_text(value, maximum)
        if len(set(values)) != len(values):
            raise ValueError("DUPLICATE_OBSERVATION")
        return values


class PixelInput(DTO):
    """Private validated derivative, never an owner-visible URL or upload permit."""

    source_sha256: Digest
    derivative_sha256: Digest
    preprocessing: Literal["exif_contain_white_rgb_png256_strip_v1"]
    content: bytes = Field(repr=False, min_length=1, max_length=262144)
