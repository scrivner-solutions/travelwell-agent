"""The loop that claims admitted events and drives their runs.

Same shape as app/services/actions/runner.py, and for the same reason: the
`FOR UPDATE SKIP LOCKED` claim is what makes concurrency safe, not the process
boundary, so several instances can run this at once.

One deliberate difference from that runner - **this one is off by default.**
The actions runner executes work a user already approved; this one calls a
model, and a loop that spends on its own is not something a deploy should
acquire by being deployed. `AGENT_WORKER=on` is the whole switch, and Admit is
still the gate underneath it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import UTC, datetime

from app.agent.admit import admit, claim_pending
from app.agent.runs import RunOutcome, run_pretrip_plan

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 5.0

_TASK_NAME = "agent-worker"


def enabled() -> bool:
    return os.getenv("AGENT_WORKER", "off").lower() in ("1", "on", "true", "yes")


def interval_seconds() -> float:
    return float(os.getenv("AGENT_WORKER_INTERVAL_S", DEFAULT_INTERVAL_SECONDS))


def _default_client():
    # Imported here, not at module scope: constructing a genai client reads
    # ambient credentials, and importing this module must not.
    from app.agent.gemini import GeminiClient, default_model

    model = default_model()
    return GeminiClient(model=model), model


async def drive_once(
    session_factory,
    *,
    client=None,
    model: str | None = None,
    now: datetime | None = None,
) -> RunOutcome | None:
    """Claim one pending event, admit it, and run it if it was accepted.

    Returns None when there was nothing to claim or the event was dropped -
    both are ordinary, and neither is worth a log line at this level.
    """
    moment = now or datetime.now(UTC)
    async with session_factory() as session:
        event = await claim_pending(session)
        if event is None:
            return None
        # admit() commits, which is also what releases the claim lock.
        run = await admit(session, event, now=moment)
        if run is None:
            return None
        if client is None:
            client, model = _default_client()
        return await run_pretrip_plan(
            session,
            trip_id=run.trip_id,
            client=client,
            model=model,
            now=moment,
            run=run,
        )


async def run_forever(session_factory, interval: float | None = None) -> None:
    delay = interval if interval is not None else interval_seconds()
    logger.info("agent worker started, %.1fs interval", delay)
    while True:
        try:
            await drive_once(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One bad tick must not end the loop; a dead worker is silent, and
            # the events it stops claiming just accumulate as `pending`.
            logger.exception("agent worker tick failed")
        await asyncio.sleep(delay)


@contextlib.asynccontextmanager
async def running(session_factory):
    """Own the worker task for the lifetime of the app."""
    if not enabled():
        logger.info("agent worker disabled (AGENT_WORKER)")
        yield None
        return
    task = asyncio.create_task(run_forever(session_factory), name=_TASK_NAME)
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
