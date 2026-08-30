"""The loop that drives approved actions to their conclusion.

An in-process asyncio task rather than a separate worker, because the claim is
what makes it safe, not the process boundary: `FOR UPDATE SKIP LOCKED` means
several instances can run this at once and each takes rows the others are not
holding. Splitting it out becomes worth doing when execution needs to scale
apart from the API, and nothing about the executor changes when it does.

Off by default under tests, which drive `drive_once` directly against a fake
clock: a loop that sleeps makes a booking test slow and, worse, flaky.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from app.services.actions.executor import drive_once

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 1.0

# Matches AGENT_DESIGN section 14's SSE cadence: the stream polls the row at 1s,
# so driving faster only produces states nothing reads.
_TASK_NAME = "actions-runner"


def enabled() -> bool:
    return os.getenv("ACTIONS_RUNNER", "on").lower() not in ("0", "off", "false", "no")


def interval_seconds() -> float:
    return float(os.getenv("ACTIONS_RUNNER_INTERVAL_S", DEFAULT_INTERVAL_SECONDS))


async def run_forever(session_factory, interval: float | None = None) -> None:
    delay = interval if interval is not None else interval_seconds()
    logger.info("actions runner started, %.1fs interval", delay)
    while True:
        try:
            await drive_once(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One bad tick must not end the loop: the next claim may be a
            # different action entirely, and a dead runner is silent.
            logger.exception("actions runner tick failed")
        await asyncio.sleep(delay)


@contextlib.asynccontextmanager
async def running(session_factory):
    """Own the runner task for the lifetime of the app."""
    if not enabled():
        logger.info("actions runner disabled (ACTIONS_RUNNER)")
        yield None
        return
    task = asyncio.create_task(run_forever(session_factory), name=_TASK_NAME)
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
