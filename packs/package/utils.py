from __future__ import annotations

import inspect

from packs.utils import (
    COMMAND_NAME_RE,
    RESERVED_COMMAND_NAMES,
    format_duration,
    pack_command_name,
)

_FORMAT_CURRENCY_SUPPORTS_BOT: bool | None = None


def format_pack_currency(amount: int, bot=None) -> str:
    """Call BallsDex's currency formatter on both 3.0 and 3.1+."""
    global _FORMAT_CURRENCY_SUPPORTS_BOT
    from settings.utils import format_currency

    if _FORMAT_CURRENCY_SUPPORTS_BOT is None:
        _FORMAT_CURRENCY_SUPPORTS_BOT = "bot" in inspect.signature(format_currency).parameters
    if _FORMAT_CURRENCY_SUPPORTS_BOT:
        return format_currency(amount, bot=bot)
    return format_currency(amount)


__all__ = [
    "COMMAND_NAME_RE",
    "RESERVED_COMMAND_NAMES",
    "format_duration",
    "format_pack_currency",
    "pack_command_name",
]
