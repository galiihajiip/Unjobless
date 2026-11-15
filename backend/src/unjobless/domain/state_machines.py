"""Explicit transition tables (docs/domain/STATE_MACHINES.md). Anything not listed is rejected."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from unjobless.core.errors import InvalidTransition
from unjobless.domain.enums import (
    AITaskStatus,
    ApplicationStatus,
    ImportItemStatus,
    PolicyStatus,
    RunStatus,
    SourceState,
    VerificationStatus,
)


@dataclass(frozen=True)
class Machine[S: StrEnum]:
    name: str
    transitions: dict[S, frozenset[S]]

    def allowed(self, src: S | None, dst: S) -> bool:
        if src is None:
            return True
        return dst in self.transitions.get(src, frozenset())

    def check(self, src: S | None, dst: S) -> None:
        if not self.allowed(src, dst):
            raise InvalidTransition(
                f"{self.name}: cannot move from {src} to {dst}", details={"from": str(src), "to": str(dst)}
            )


def _t[S: StrEnum](pairs: Iterable[tuple[S, Iterable[S]]]) -> dict[S, frozenset[S]]:
    return {k: frozenset(v) for k, v in pairs}


SS = SourceState
SOURCE_STATE = Machine(
    "source_state",
    _t(
        [
            (SS.DISABLED, [SS.ENABLED]),
            (SS.ENABLED, [SS.PAUSED, SS.DISABLED]),
            (SS.PAUSED, [SS.ENABLED, SS.DISABLED]),
        ]
    ),
)
ENABLEABLE_POLICIES = frozenset({PolicyStatus.APPROVED, PolicyStatus.RESTRICTED})

R = RunStatus
RUN = Machine(
    "run",
    _t(
        [
            (R.QUEUED, [R.RUNNING, R.CANCELLED, R.FAILED]),
            (R.RUNNING, [R.SUCCEEDED, R.PARTIAL, R.RETRY_SCHEDULED, R.FAILED, R.CANCELLED]),
            (R.RETRY_SCHEDULED, [R.QUEUED, R.RUNNING, R.CANCELLED, R.FAILED]),
        ]
    ),
)
TERMINAL_RUN = frozenset({R.SUCCEEDED, R.PARTIAL, R.FAILED, R.CANCELLED})

I = ImportItemStatus  # noqa: E741
IMPORT_ITEM = Machine(
    "import_item",
    _t(
        [
            (I.QUEUED, [I.BLOCKED, I.FETCHING, I.EXTRACTED, I.FAILED, I.UNAVAILABLE, I.DUPLICATE]),
            (I.FETCHING, [I.UNAVAILABLE, I.FAILED, I.EXTRACTED, I.BLOCKED]),
            (I.EXTRACTED, [I.DUPLICATE, I.NEEDS_REVIEW, I.FAILED]),
            (I.NEEDS_REVIEW, [I.SAVED, I.REJECTED, I.DUPLICATE, I.NEEDS_REVIEW]),
            (I.UNAVAILABLE, [I.QUEUED]),
            (I.FAILED, [I.QUEUED]),
            (I.BLOCKED, [I.QUEUED]),
            (I.DUPLICATE, [I.NEEDS_REVIEW]),
            (I.REJECTED, [I.NEEDS_REVIEW]),
        ]
    ),
)
TERMINAL_IMPORT_OK = frozenset({I.SAVED, I.DUPLICATE, I.REJECTED, I.NEEDS_REVIEW})
TERMINAL_IMPORT_ERR = frozenset({I.BLOCKED, I.UNAVAILABLE, I.FAILED})

V = VerificationStatus
VERIFICATION = Machine(
    "verification",
    _t(
        [
            (
                V.NEW_UNREVIEWED,
                [
                    V.NEEDS_REVIEW,
                    V.POTENTIAL_LEAD,
                    V.LIKELY_OPEN,
                    V.VERIFIED_OPEN,
                    V.REJECTED_AS_IRRELEVANT,
                    V.EXPIRED,
                    V.STATUS_UNKNOWN,
                    V.CLOSED,
                ],
            ),
            (
                V.NEEDS_REVIEW,
                [V.VERIFIED_OPEN, V.POTENTIAL_LEAD, V.REJECTED_AS_IRRELEVANT, V.LIKELY_OPEN, V.EXPIRED],
            ),
            (V.POTENTIAL_LEAD, [V.VERIFIED_OPEN, V.REJECTED_AS_IRRELEVANT, V.EXPIRED, V.NEEDS_REVIEW]),
            (V.LIKELY_OPEN, [V.VERIFIED_OPEN, V.STATUS_UNKNOWN, V.CLOSED, V.EXPIRED]),
            (V.VERIFIED_OPEN, [V.LIKELY_OPEN, V.STATUS_UNKNOWN, V.CLOSED, V.EXPIRED]),
            (V.STATUS_UNKNOWN, [V.VERIFIED_OPEN, V.LIKELY_OPEN, V.SOURCE_UNAVAILABLE, V.CLOSED, V.EXPIRED]),
            (V.SOURCE_UNAVAILABLE, [V.VERIFIED_OPEN, V.LIKELY_OPEN, V.CLOSED, V.EXPIRED, V.STATUS_UNKNOWN]),
            (V.CLOSED, [V.VERIFIED_OPEN]),
            (V.EXPIRED, [V.VERIFIED_OPEN]),
            (V.REJECTED_AS_IRRELEVANT, [V.NEEDS_REVIEW]),
        ]
    ),
)
OPEN_STATUSES = frozenset({V.VERIFIED_OPEN, V.LIKELY_OPEN})

A = ApplicationStatus
_NON_TERMINAL_APP = [A.SAVED, A.SHORTLISTED, A.PREPARING, A.APPLIED, A.ASSESSMENT, A.INTERVIEW, A.OFFER]
_app = {
    A.SAVED: {A.SHORTLISTED, A.PREPARING},
    A.SHORTLISTED: {A.PREPARING, A.SAVED},
    A.PREPARING: {A.APPLIED, A.SHORTLISTED},
    A.APPLIED: {A.ASSESSMENT, A.INTERVIEW, A.REJECTED, A.OFFER},
    A.ASSESSMENT: {A.INTERVIEW, A.REJECTED, A.OFFER},
    A.INTERVIEW: {A.INTERVIEW, A.OFFER, A.REJECTED},
    A.OFFER: {A.ARCHIVED},
    A.REJECTED: {A.ARCHIVED},
    A.WITHDRAWN: {A.ARCHIVED},
    A.ARCHIVED: {A.SAVED},
}
for s in _NON_TERMINAL_APP:
    _app[s] |= {A.WITHDRAWN, A.ARCHIVED}
APPLICATION = Machine("application", {k: frozenset(v) for k, v in _app.items()})

T = AITaskStatus
AI_TASK = Machine(
    "ai_task",
    _t(
        [
            (T.PENDING, [T.RUNNING, T.CANCELLED, T.FAILED_PROVIDER, T.RATE_LIMITED]),
            (T.RUNNING, [T.SUCCEEDED, T.RUNNING, T.FAILED_VALIDATION, T.RATE_LIMITED, T.FAILED_PROVIDER]),
            (T.RATE_LIMITED, [T.PENDING]),
        ]
    ),
)
