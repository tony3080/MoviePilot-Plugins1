"""Domain states shared by the RSS All-in-One plugin services."""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class MediaState(str, Enum):
    DISCOVERED = "discovered"
    IDENTIFIED = "identified"
    UNIDENTIFIED = "unidentified"
    EXISTING = "existing"
    PENDING = "pending"
    IMPORTING = "importing"
    IMPORTED = "imported"
    ROLLED_BACK = "rolled_back"


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WatchState(str, Enum):
    WAITING_TASK = "waiting_task"
    WATCHING = "watching"
    WAITING_LIBRARY = "waiting_library"
    ROLLING_BACK = "rolling_back"
    DONE = "done"
    ROLLED_BACK = "rolled_back"
    RISK_CONTROL = "risk_control"
    ERROR = "error"


MEDIA_TRANSITIONS: Dict[MediaState, FrozenSet[MediaState]] = {
    MediaState.DISCOVERED: frozenset({
        MediaState.IDENTIFIED,
        MediaState.UNIDENTIFIED,
        MediaState.EXISTING,
    }),
    MediaState.UNIDENTIFIED: frozenset({
        MediaState.IDENTIFIED,
        MediaState.EXISTING,
    }),
    MediaState.IDENTIFIED: frozenset({
        MediaState.UNIDENTIFIED,
        MediaState.EXISTING,
        MediaState.PENDING,
        MediaState.IMPORTING,
    }),
    MediaState.EXISTING: frozenset({
        MediaState.IDENTIFIED,
        MediaState.PENDING,
    }),
    MediaState.PENDING: frozenset({
        MediaState.IDENTIFIED,
        MediaState.IMPORTING,
    }),
    MediaState.IMPORTING: frozenset({
        MediaState.IDENTIFIED,
        MediaState.IMPORTED,
        MediaState.ROLLED_BACK,
    }),
    MediaState.IMPORTED: frozenset({MediaState.ROLLED_BACK}),
    MediaState.ROLLED_BACK: frozenset({
        MediaState.IDENTIFIED,
        MediaState.PENDING,
        MediaState.IMPORTING,
    }),
}


def can_transition(current: str, target: str) -> bool:
    """Return whether a media item may move between two persisted states."""
    try:
        source_state = MediaState(current)
        target_state = MediaState(target)
    except ValueError:
        return False
    return target_state in MEDIA_TRANSITIONS[source_state]


def validate_season(value: object) -> int | None:
    """Normalize an optional season number while preserving specials as season zero."""
    if value in (None, ""):
        return None
    try:
        season = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("季号必须是大于等于 0 的整数") from error
    if season < 0:
        raise ValueError("季号必须是大于等于 0 的整数")
    return season
