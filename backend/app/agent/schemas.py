"""The two schemas the model sits between, and the checks that guard the second.

`TripContext` is everything the model is allowed to see. `PlanProposal` is
everything it is allowed to say. They live together rather than beside the code
that builds each, because the pair *is* the narrow waist: the model's entire
influence on the world is one `PlanProposal` value, and every identifier in it
has to resolve against the `TripContext` that was actually sent. Reading one
without the other tells you nothing about what the model can do.

Verify (pipeline stage 6) is here for the same reason - it is the function that
enforces that sentence and it needs both schemas in front of it.

Two tiers, failing differently on purpose:

- **Structural** (ids, times, states, ranks) produces `Violation`s and routes to
  Repair. The database CHECKs are the backstop, not the error surface: anything
  Postgres would reject has to fail here first, with a code that names it.
- **Prose** (headline, reason, rejection_reason, gap_explanation) is sanitized
  in code and **never fails a run**. Degrading prose is acceptable; degrading
  structure is not.

Strictness differs between the two schemas and the difference is deliberate.
`PlanProposal` becomes the provider's `responseJsonSchema`, so it stays flat -
no optional unions, no deep `$defs` - and every string and list is capped, which
bounds output tokens and matches what the UI can render. `TripContext` is only
ever serialized as a payload, never handed over as a schema, so it can carry the
nullable fields the domain actually has.
"""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

# `additionalProperties: false` on every object: required by structured-output
# mode, and it is what stops the model adding a field we would then have to
# decide whether to trust.
_STRICT = ConfigDict(extra="forbid")

# Trip-local wall clock. The model never sees a UTC instant or an offset;
# timezone conversion is code's job (determinism ledger).
TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"

MAX_ITEMS = 12
MAX_OPTIONS_PER_ITEM = 4


# --------------------------------------------------------------------------
# TripContext: what the model sees, and what `agent_runs.context_snapshot` is
# --------------------------------------------------------------------------


class ContextMeta(BaseModel):
    model_config = _STRICT

    prompt_version: str
    generated_at: str
    run_kind: str
    # e.g. ["places_timeout:w3"]. A partially gathered context still runs; the
    # model and the replay both need to know it was incomplete.
    degraded: list[str] = Field(default_factory=list)


class Hotel(BaseModel):
    model_config = _STRICT

    name: str
    lat: float | None = None
    lng: float | None = None


class TripFacts(BaseModel):
    model_config = _STRICT

    destination: str
    label: str | None = None
    start_date: date
    end_date: date
    timezone: str
    hotel: Hotel | None = None


class Commitment(BaseModel):
    """Projected, not passed through: title, day, start, end and nothing else.

    No attendees, no description, no conference link. Every field the model
    cannot act on is pure cost plus one more thing to hallucinate about.
    """

    model_config = _STRICT

    id: str
    title: str
    day: date
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)


class ContextWindow(BaseModel):
    model_config = _STRICT

    id: str
    day: date
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)
    minutes: int
    bounded_by: list[str] = Field(default_factory=list)


class SessionMinutes(BaseModel):
    model_config = _STRICT

    min: int
    max: int


class ContextPreferences(BaseModel):
    model_config = _STRICT

    dietary: list[str] = Field(default_factory=list)
    workout_kinds: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    memberships: list[str] = Field(default_factory=list)
    price_level_max: int | None = None
    day_pass_max_cents: int | None = None
    session_minutes: SessionMinutes | None = None
    preferred_times: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    """One eligible place, projected into exactly these fields.

    A single raw Places result is larger than this entire list. `window_ids` is
    the set of windows this candidate passed the hard filters for, which is what
    makes `candidate_window_mismatch` checkable.
    """

    model_config = _STRICT

    id: str
    kind: str
    window_ids: list[str]
    name: str
    summary: str | None = None
    walk_minutes: int | None = None
    day_pass_cents: int | None = None
    price_level: int | None = None
    amenities: list[str] = Field(default_factory=list)
    # Hard constraints our records could not answer for this place. Admitted
    # rather than dropped (decision 8); the tokens are `candidates.UNKNOWN_*`.
    unknown: list[str] = Field(default_factory=list)
    open: str | None = None


class CurrentPlanItem(BaseModel):
    model_config = _STRICT

    item_id: str
    window_id: str | None = None
    name: str
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)
    status: str


class CurrentPlanSummary(BaseModel):
    """Summary only, never full history - the budget says 500 tokens."""

    model_config = _STRICT

    version: int
    headline: str | None = None
    items: list[CurrentPlanItem] = Field(default_factory=list)


class TripContext(BaseModel):
    model_config = _STRICT

    meta: ContextMeta
    trip: TripFacts
    commitments: list[Commitment] = Field(default_factory=list)
    windows: list[ContextWindow] = Field(default_factory=list)
    preferences: ContextPreferences
    candidates: list[Candidate] = Field(default_factory=list)
    current_plan: CurrentPlanSummary | None = None

    def is_empty_decision_space(self) -> bool:
        """No windows, or no window any candidate can fill.

        The pipeline skips stages 3 through 7 entirely on a true here and
        commits a code-generated empty plan. A model call with nothing to choose
        from buys nothing and adds a hallucination opportunity.
        """
        if not self.windows:
            return True
        reachable = {wid for c in self.candidates for wid in c.window_ids}
        return not any(w.id in reachable for w in self.windows)

    def preference_vocabulary(self) -> frozenset[str]:
        """Every token `matched_preferences` may legally cite.

        Derived rather than listed, so the vocabulary cannot drift from the
        preferences actually sent.
        """
        p = self.preferences
        tokens = {
            *p.dietary,
            *p.workout_kinds,
            *p.facilities,
            *p.memberships,
            *p.preferred_times,
        }
        if p.session_minutes is not None:
            tokens.add(session_token(p.session_minutes))
        return frozenset(tokens)


def session_token(minutes: SessionMinutes) -> str:
    """The one derived vocabulary token, e.g. "45-90 min"."""
    return f"{minutes.min}-{minutes.max} min"


# --------------------------------------------------------------------------
# PlanProposal: everything the model is allowed to say
# --------------------------------------------------------------------------


class ProposedOption(BaseModel):
    """Field order is deliberate: justification precedes verdict.

    `rejection_reason` is an empty string rather than null when absent. That
    keeps the JSON schema flat - a nullable field costs an `anyOf` the provider
    then has to reason about - and Bind writes NULL for the empty string, which
    is what the `plan_item_options` CHECK expects.
    """

    model_config = _STRICT

    candidate_id: str = Field(max_length=64)
    reason: str = Field(default="", max_length=280)
    matched_preferences: list[str] = Field(default_factory=list, max_length=8)
    rejection_reason: str = Field(default="", max_length=280)
    state: str = Field(pattern=r"^(selected|alternative|rejected)$")
    rank: int = Field(ge=1, le=MAX_OPTIONS_PER_ITEM)


class ProposedItem(BaseModel):
    model_config = _STRICT

    window_id: str = Field(max_length=64)
    kind: str = Field(pattern=r"^(activity|meal)$")
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)
    options: list[ProposedOption] = Field(min_length=1, max_length=MAX_OPTIONS_PER_ITEM)


class WindowNote(BaseModel):
    model_config = _STRICT

    window_id: str = Field(max_length=64)
    gap_explanation: str = Field(default="", max_length=200)


class PlanProposal(BaseModel):
    model_config = _STRICT

    headline: str = Field(default="", max_length=120)
    window_notes: list[WindowNote] = Field(default_factory=list, max_length=MAX_ITEMS)
    items: list[ProposedItem] = Field(default_factory=list, max_length=MAX_ITEMS)


# --------------------------------------------------------------------------
# Verify
# --------------------------------------------------------------------------


class ViolationCode(enum.StrEnum):
    """Named so a repair turn can be told what was wrong in our vocabulary."""

    unknown_window = "unknown_window"
    unknown_candidate = "unknown_candidate"
    candidate_window_mismatch = "candidate_window_mismatch"
    outside_window = "outside_window"
    duration_out_of_range = "duration_out_of_range"
    overlapping_items = "overlapping_items"
    no_selected = "no_selected"
    multiple_selected = "multiple_selected"
    rejection_reason_missing = "rejection_reason_missing"
    duplicate_rank = "duplicate_rank"
    hard_preference_violation = "hard_preference_violation"
    unknown_preference_token = "unknown_preference_token"
    # Not in AGENT_DESIGN.md's table, which assumes a payload that already
    # matched the schema. With structured outputs this should be unreachable;
    # if it fires, the provider ignored the schema.
    schema_mismatch = "schema_mismatch"


@dataclass(frozen=True)
class Violation:
    code: ViolationCode
    path: str
    detail: str


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


# --------------------------------------------------------------------------
# Prose sanitizers. These never fail a run.
# --------------------------------------------------------------------------

_MARKUP = re.compile(r"[*_`#>\[\]{}|~]")
# The UI never speaks as "I" - that is a project copy convention, not a style
# preference, and the model has no way to know it from the payload alone.
_AGENT_VOICE = re.compile(r"\bI\b|\bI'(m|ve|ll|d)\b|\b(me|my|mine|we|our|us)\b")
# Substituted when the sanitizer empties a rejection reason, because the
# `plan_item_options` CHECK requires a rejected option to carry one. Degrading
# to a flat sentence beats failing a run over a pronoun.
REJECTION_FALLBACK = "Not the best fit for this window."


def sanitize_prose(text: str, limit: int, *, fallback: str = "") -> str:
    """Strip control characters and markup, reject agent voice, truncate.

    Returns `fallback` when nothing usable survives, so a caller that needs a
    non-empty string can say so rather than checking afterwards.
    """
    cleaned = "".join(
        ch for ch in text if ch == " " or unicodedata.category(ch)[0] != "C"
    )
    cleaned = _MARKUP.sub("", cleaned)
    cleaned = " ".join(cleaned.split())
    if _AGENT_VOICE.search(cleaned):
        return fallback
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip()
    return cleaned or fallback


def sanitize_proposal(proposal: PlanProposal) -> PlanProposal:
    """Apply the prose tier. Structure is untouched."""
    proposal.headline = sanitize_prose(proposal.headline, 120)
    for note in proposal.window_notes:
        note.gap_explanation = sanitize_prose(note.gap_explanation, 200)
    for item in proposal.items:
        for option in item.options:
            option.reason = sanitize_prose(option.reason, 280)
            if option.rejection_reason:
                option.rejection_reason = sanitize_prose(
                    option.rejection_reason, 280, fallback=REJECTION_FALLBACK
                )
    return proposal


def verify(payload: dict, ctx: TripContext) -> PlanProposal | list[Violation]:
    """Payload in, a sanitized `PlanProposal` or the violations that stopped it.

    Structural checks run against the raw parse and prose is sanitized only
    after they pass. The order matters: sanitizing first can empty a rejection
    reason, which would then fail `rejection_reason_missing` - a prose problem
    reported as a structural one, and a run failed by the tier that is supposed
    never to fail one.
    """
    try:
        proposal = PlanProposal.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError, or a non-dict payload
        return [
            Violation(ViolationCode.schema_mismatch, "$", str(exc).splitlines()[0])
        ]

    violations = _structural_violations(proposal, ctx)
    if violations:
        return violations
    return sanitize_proposal(proposal)


def _structural_violations(
    proposal: PlanProposal, ctx: TripContext
) -> list[Violation]:
    windows = {w.id: w for w in ctx.windows}
    candidates = {c.id: c for c in ctx.candidates}
    vocabulary = ctx.preference_vocabulary()
    prefs = ctx.preferences
    out: list[Violation] = []
    placed: list[tuple[date, int, int, str]] = []

    for i, item in enumerate(proposal.items):
        path = f"items[{i}]"
        window = windows.get(item.window_id)
        if window is None:
            out.append(
                Violation(
                    ViolationCode.unknown_window,
                    path,
                    f"{item.window_id!r} is not a window in this context",
                )
            )
            continue

        start, end = to_minutes(item.start), to_minutes(item.end)
        w_start, w_end = to_minutes(window.start), to_minutes(window.end)
        if start < w_start or end > w_end or end <= start:
            out.append(
                Violation(
                    ViolationCode.outside_window,
                    path,
                    f"{item.start}-{item.end} is not inside "
                    f"{window.start}-{window.end}",
                )
            )
        elif item.kind == "activity" and prefs.session_minutes is not None:
            duration = end - start
            bounds = prefs.session_minutes
            if not bounds.min <= duration <= bounds.max:
                out.append(
                    Violation(
                        ViolationCode.duration_out_of_range,
                        path,
                        f"{duration} min is outside {bounds.min}-{bounds.max}",
                    )
                )
        placed.append((window.day, start, end, path))
        out.extend(_option_violations(item, path, window.id, candidates, prefs, vocabulary))

    out.extend(_overlap_violations(placed))
    return out


def _option_violations(
    item: ProposedItem,
    path: str,
    window_id: str,
    candidates: dict[str, Candidate],
    prefs: ContextPreferences,
    vocabulary: frozenset[str],
) -> list[Violation]:
    out: list[Violation] = []
    selected = [o for o in item.options if o.state == "selected"]
    if not selected:
        out.append(
            Violation(ViolationCode.no_selected, path, "no option is selected")
        )
    elif len(selected) > 1:
        out.append(
            Violation(
                ViolationCode.multiple_selected,
                path,
                f"{len(selected)} options are selected",
            )
        )

    ranks = [o.rank for o in item.options]
    if len(set(ranks)) != len(ranks):
        out.append(
            Violation(ViolationCode.duplicate_rank, path, f"ranks {sorted(ranks)}")
        )

    for j, option in enumerate(item.options):
        opath = f"{path}.options[{j}]"
        if option.state == "rejected" and not option.rejection_reason.strip():
            out.append(
                Violation(
                    ViolationCode.rejection_reason_missing,
                    opath,
                    "rejected without a reason",
                )
            )
        unknown = [t for t in option.matched_preferences if t not in vocabulary]
        if unknown:
            out.append(
                Violation(
                    ViolationCode.unknown_preference_token,
                    opath,
                    f"{unknown} not in the context vocabulary",
                )
            )

        candidate = candidates.get(option.candidate_id)
        if candidate is None:
            out.append(
                Violation(
                    ViolationCode.unknown_candidate,
                    opath,
                    f"{option.candidate_id!r} is not a candidate in this context",
                )
            )
            continue
        if window_id not in candidate.window_ids:
            out.append(
                Violation(
                    ViolationCode.candidate_window_mismatch,
                    opath,
                    f"{candidate.id} was not fetched for {window_id}",
                )
            )
        if option.state == "selected":
            out.extend(_hard_preference_violations(candidate, item, prefs, opath))
    return out


def _hard_preference_violations(
    candidate: Candidate,
    item: ProposedItem,
    prefs: ContextPreferences,
    path: str,
) -> list[Violation]:
    """A backstop, not the filter.

    `candidates.py` already applied these at query time, so a selected option
    breaking one means the model reached outside the candidate set - which
    `unknown_candidate` would normally have caught first. It is cheap and it
    fails loudly if the two ever disagree.

    Memberships are not checked: in our preferences they are enabling (a YMCA
    membership makes a place free), never constraining, so there is nothing for
    a selection to break.
    """
    out: list[Violation] = []
    if (
        prefs.day_pass_max_cents is not None
        and candidate.day_pass_cents is not None
        and candidate.day_pass_cents > prefs.day_pass_max_cents
    ):
        out.append(
            Violation(
                ViolationCode.hard_preference_violation,
                path,
                f"{candidate.day_pass_cents}c is over the "
                f"{prefs.day_pass_max_cents}c day pass cap",
            )
        )
    if (
        prefs.price_level_max is not None
        and candidate.price_level is not None
        and candidate.price_level > prefs.price_level_max
    ):
        out.append(
            Violation(
                ViolationCode.hard_preference_violation,
                path,
                f"price level {candidate.price_level} is over "
                f"{prefs.price_level_max}",
            )
        )
    # Known-bad only, mirroring `passes_hard_filters`. A candidate carrying the
    # `dietary` unknown was admitted deliberately, so failing it here would
    # reject the model for choosing what the filter handed it - the exact
    # disagreement this backstop exists to catch, pointed the wrong way.
    if (
        item.kind == "meal"
        and prefs.dietary
        and candidate.amenities
        and not set(prefs.dietary) & set(candidate.amenities)
    ):
        out.append(
            Violation(
                ViolationCode.hard_preference_violation,
                path,
                f"{candidate.name} meets none of {prefs.dietary}",
            )
        )
    return out


def _overlap_violations(
    placed: list[tuple[date, int, int, str]],
) -> list[Violation]:
    out: list[Violation] = []
    ordered = sorted(placed, key=lambda p: (p[0], p[1]))
    for (day_a, _, end_a, path_a), (day_b, start_b, _, path_b) in pairwise(ordered):
        if day_a == day_b and start_b < end_a:
            out.append(
                Violation(
                    ViolationCode.overlapping_items,
                    path_b,
                    f"overlaps {path_a} on {day_a}",
                )
            )
    return out
