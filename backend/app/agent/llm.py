"""The provider seam, and the fake that keeps the rest of the pipeline testable.

Stage 4 is the one non-deterministic stage in a run, so it is the one worth
putting behind a interface: nine of the ten stages are ordinary functions with a
fixed input and a fixed output, and they only stay that way if nothing else in
`app/agent/` can reach a network. This module is the only place a provider SDK
is ever imported.

`LlmRequest` is built by Frame and is pure data, which is what makes replay a
diff rather than a guess: the same `TripContext` produces byte-identical
payloads, because serialization is canonical and the system prompt is a frozen
constant with nothing interpolated into it.

A repair is a second turn in the same request thread rather than a fresh
attempt, so `turns` carries it. Two attempts from a clean slate would throw away
the reasoning that produced the near-miss, which is the only thing that makes
the second one likely to be better.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class LlmRequest:
    """Exactly what goes over the wire, minus the SDK's own framing."""

    model: str
    system: str
    payload: str
    output_schema: type[BaseModel]
    effort: str = "high"
    # Module-level constants in sorted order, never built per user or per
    # request: the cacheable prefix renders as tools, then system, then
    # messages, and any byte change invalidates everything after it.
    tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class LlmResponse:
    """The provider's answer, normalised.

    `stop_reason` is checked before the body is parsed. A truncated structured
    output is invalid JSON, and reporting that as a parse failure sends whoever
    reads the run after a schema problem that is not there.
    """

    text: str
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)


class LlmClient(Protocol):
    async def complete(
        self, request: LlmRequest, *, turns: Sequence[str] = ()
    ) -> LlmResponse: ...


class FakeLLM:
    """Scripted responses, in order, with every request recorded.

    Deliberately strict about running out: a pipeline that calls the model more
    times than the test scripted is a pipeline doing something the test did not
    mean to assert, and returning a default would hide exactly the bug worth
    catching - a repair loop that does not terminate.
    """

    def __init__(self, responses: Sequence[LlmResponse | str]) -> None:
        self._queued = [
            r if isinstance(r, LlmResponse) else LlmResponse(text=r)
            for r in responses
        ]
        self.calls: list[tuple[LlmRequest, tuple[str, ...]]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def complete(
        self, request: LlmRequest, *, turns: Sequence[str] = ()
    ) -> LlmResponse:
        self.calls.append((request, tuple(turns)))
        if not self._queued:
            raise AssertionError(
                f"FakeLLM ran out of scripted responses on call {len(self.calls)}"
            )
        return self._queued.pop(0)
