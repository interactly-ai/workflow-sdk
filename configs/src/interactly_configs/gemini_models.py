"""Gemini thinking levels.

Mirrors the one class `GoogleLLMConfig.thinking_level` is typed with. Upstream keeps it in a file of
server-side tuning tables (per-model token budgets, which levels each model offers); those tables
carry no config shape and are not vendored, so this module holds the enum alone.
"""

from enum import Enum


class GeminiThinkingLevel(str, Enum):
    """Every level any Gemini model accepts, as an enum so editors can render a select.

    Which of these a *given* model offers is narrower than this union: MINIMAL is Flash-only, and
    not every Flash model has it (`gemini-3.7-flash` starts at LOW). The server rejects a level the
    chosen model does not offer.
    """

    MINIMAL = "MINIMAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
