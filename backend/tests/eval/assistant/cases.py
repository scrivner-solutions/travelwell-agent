"""The eval case: what was said, against what trip, and what must come of it.

A case is data; the trip it runs against is code. `scene` is a registry key the
runner resolves to a fixture factory, because a two-day Chicago trip with three
commitments is not expressible in JSON and should not be attempted.

Three things here are load-bearing and none of them are obvious:

- **Items are named, never identified.** Item ids are UUIDs minted when the
  fixture builds, so a case that stored one would pass once. Cases refer to the
  item the traveler and the model both see: its name.
- **A case is a sequence of turns, from the first commit.** The assistant has
  no conversational memory, but the plan rows do: turn 2 runs against the state
  turn 1 left. "Skip the gym" then "put it back" is a real two-turn case that is
  testable today, and retrofitting sequence support into a single-shot runner is
  the expensive version of this file.
- **A recording proves it is answering the same question.** `frame_utterance`
  serializes with `sort_keys` and interpolates nothing into the system prompt,
  so the same context yields byte-identical input. Hashing those bytes turns a
  stale recording into a loud mismatch instead of a quiet wrong answer.

Where the model's words come from is `mode`, and it decides what a case proves:
a scripted decision tests the *controller*, a live one tests the *prompt*. A
suite that conflates them is green and worthless.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import ItemStatus

_STRICT = ConfigDict(extra="forbid")

# `apply_decision` emits a bare `not_in_plan` and `status:<value>` for everything
# else; the asymmetry is real, and a typo'd code in a case file would otherwise
# assert nothing while looking like it asserted something. Derived from the enum
# rather than listed, because the first hand-written copy of this list was
# already missing a member.
REFUSAL_CODES = frozenset(
    {"not_in_plan", *(f"status:{s.value}" for s in ItemStatus)}
)

# A refusal whose id matched no row we could name comes back with `name=""`.
UNRESOLVED = "<unknown>"

# Resolved off this module so a runner invoked from any cwd finds the same
# files. Recordings sit beside the cases they belong to.
SUITE_DIR = Path(__file__).parent / "suite"
RECORDINGS_DIR = Path(__file__).parent / "recordings"

# A scripted response has the same problem a case does: it must name an item
# whose id does not exist until the fixture builds. It stays a raw string rather
# than a typed object, because scripting *malformed* output is how Verify gets
# tested, so the reference is a placeholder the runner substitutes.
ITEM_REF = re.compile(r"\{\{item:([^{}]+)\}\}")


def item_refs(scripted: str) -> list[str]:
    return ITEM_REF.findall(scripted)


def bind_items(scripted: str, ids: dict[str, str]) -> str:
    """Placeholder to real id, raising on a name the fixture does not have.

    Substituting nothing would turn a case about a real item into a case about
    an empty string, which passes for the wrong reason.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in ids:
            raise KeyError(f"scripted response names an item not in the plan: {name!r}")
        return ids[name]

    return ITEM_REF.sub(replace, scripted)


def render_scripted(entry: str | dict) -> str:
    """An object becomes canonical JSON; a string is already what we mean."""
    return entry if isinstance(entry, str) else json.dumps(entry, sort_keys=True)


class ExpectedChange(BaseModel):
    """One row the controller must have moved."""

    model_config = _STRICT

    item: str = Field(min_length=1)
    # A `Literal` for the same reason `AssistantAction.kind` is one: today's
    # only verb produces one status, and a second verb is a second member.
    status: Literal["skipped"] = "skipped"


class ExpectedRefusal(BaseModel):
    model_config = _STRICT

    code: str
    item: str = UNRESOLVED

    @model_validator(mode="after")
    def _known_code(self) -> ExpectedRefusal:
        if self.code not in REFUSAL_CODES:
            raise ValueError(f"unknown refusal code {self.code!r}")
        return self


class ReplyExpectation(BaseModel):
    """Properties of the sentence, never the sentence itself.

    `omits` is the load-bearing half. The measured failure this harness exists
    to catch is a reply that reports a change the controller refused, so the
    assertion worth writing is that the word "removed" is absent.
    """

    model_config = _STRICT

    mentions: list[str] = Field(default_factory=list)
    omits: list[str] = Field(default_factory=list)
    # None = unasserted. True is a case built to fail: the assistant can render
    # a question but has nowhere to hear the answer.
    is_question: bool | None = None
    # Rubric for the LLM judge, prose quality only. A judge cannot assert which
    # item moved; that is what `applied` and `refused` are for.
    judge: str = ""


class Expectation(BaseModel):
    model_config = _STRICT

    applied: list[ExpectedChange] = Field(default_factory=list)
    refused: list[ExpectedRefusal] = Field(default_factory=list)
    reply: ReplyExpectation = Field(default_factory=ReplyExpectation)
    # False asserts the model was never called - the empty-plan short circuit
    # spends nothing, and a regression there is a billing regression.
    invoked: bool | None = None
    # A `RunFailed` code when the turn is expected to raise rather than answer.
    raises: str = ""


class Turn(BaseModel):
    """One `respond()` call against the trip as the previous turn left it."""

    model_config = _STRICT

    utterance: str = Field(min_length=1)
    # Model responses in call order, because a repair is a second call. `[]` is
    # meaningful and strict: it asserts no call happens at all. An object is
    # serialized and stays readable in the file; a string goes to the model seam
    # verbatim, which is the only way to script the malformed output that Verify
    # exists to reject.
    scripted: list[str | dict] | None = None
    expect: Expectation

    def bodies(self, ids: dict[str, str]) -> list[str]:
        """Wire-ready response bodies with item placeholders resolved."""
        return [bind_items(render_scripted(e), ids) for e in self.scripted or []]


class Case(BaseModel):
    model_config = _STRICT

    id: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    # controller: scripted only, free, CI-safe, proves what the controller does
    #   with a decision.
    # prompt: live or recorded only, proves the prompt produces the right
    #   decision. This is the mode section 2's definition of done requires.
    # both: carries a script for CI and can also be graded live.
    mode: Literal["controller", "prompt", "both"]
    turns: list[Turn] = Field(min_length=1)
    note: str = ""

    @model_validator(mode="after")
    def _script_matches_mode(self) -> Case:
        for index, turn in enumerate(self.turns):
            scripted = turn.scripted is not None
            if self.mode == "prompt" and scripted:
                raise ValueError(
                    f"{self.id} turn {index}: prompt-mode cases take their words "
                    "from the model, so a script would test nothing"
                )
            if self.mode in ("controller", "both") and not scripted:
                raise ValueError(
                    f"{self.id} turn {index}: {self.mode}-mode needs a scripted "
                    "response; omit it only in prompt mode"
                )
        return self


class Suite(BaseModel):
    model_config = _STRICT

    cases: list[Case] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> Suite:
        seen = [c.id for c in self.cases]
        duplicates = {i for i in seen if seen.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate case ids: {sorted(duplicates)}")
        return self


# --------------------------------------------------------------------------
# Recordings
# --------------------------------------------------------------------------


class Recording(BaseModel):
    """What a real model said, and proof of what it was asked.

    Kept per prompt version rather than overwritten: changing the prompt does
    not make a recording wrong, it makes it a recording of a different question.
    """

    model_config = _STRICT

    case_id: str
    turn_index: int
    prompt_version: str
    model: str
    # sha256 over the exact bytes framed for the provider. Serialization is
    # canonical and the system prompt is a frozen constant, so a difference here
    # means the question changed, not that the model was moody.
    request_digest: str
    responses: list[str]
    usage: dict[str, int] = Field(default_factory=dict)
    recorded_at: str


def digest_of(system: str, payload: str) -> str:
    """The identity of a model input, over the two fields that carry meaning."""
    body = json.dumps({"system": system, "payload": payload}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def recording_path(root: Path, prompt_version: str, case_id: str, turn: int) -> Path:
    """Versioned directory, so a prompt bump orphans the whole set visibly."""
    return root / prompt_version / case_id / f"turn-{turn}.json"


def load_suite(path: Path | str) -> Suite:
    return Suite.model_validate_json(Path(path).read_text())
