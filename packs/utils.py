from __future__ import annotations

import re

RESERVED_COMMAND_NAMES = frozenset(
    {
        "claim",
        "give",
        "info",
        "list",
        "open",
        "shop",
    }
)

COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def format_duration(seconds: float) -> str:
    """Human-readable duration, including seconds for short cooldowns."""
    total = max(0, int(round(seconds)))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def pack_command_name(pack_type: str) -> str | None:
    """Return a valid Discord command name for a pack, or None if it cannot be used."""
    name = pack_type.strip().lower().replace(" ", "_")
    if not COMMAND_NAME_RE.fullmatch(name):
        return None
    if name in RESERVED_COMMAND_NAMES:
        return None
    return name
