"""Drive one agent run from the command line.

No endpoint fires a run until the admission slice lands, so this is how a run
gets started - and it doubles as the staging probe for whether Vertex is
actually reachable as the runtime service account.

Usage (from backend/, with migrations applied):
    uv run python scripts/run_agent.py --check
    uv run python scripts/run_agent.py --trip <uuid> --dry-run
    uv run python scripts/run_agent.py --trip <uuid>

`--check` runs the preflight and exits. `--dry-run` gathers and frames but never
calls the model, which is the whole pipeline minus the only stage that costs
money.

The preflight exists because "it failed" is three different situations with
three different owners, and the exit codes say which:

    0  ok
    2  not configured        - nobody set the env vars. Ours to fix.
    3  configured, refused   - credentials resolved and the API said no. An IAM
                              grant, and not something code can fix.
    4  our bug               - anything else.

It prints the resolved ADC principal before making a call, because ADC is
ambient: locally it resolves to a human account and on Cloud Run to the runtime
service account. A local pass says nothing about staging unless you can see
which principal passed.
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv

NOT_CONFIGURED = 2
REFUSED = 3
OUR_BUG = 4


def resolve_principal() -> tuple[str, str]:
    """Who ADC resolves to, and how confident we are about it.

    Returns the principal and the method, so a caller can tell "the API told us"
    from "we read it off the credential object" from "we could not find out".
    Deliberately never guesses: a wrong principal here is worse than none,
    because the entire point is to stop presuming who is authenticated.
    """
    try:
        import google.auth
        import google.auth.transport.requests as auth_requests
    except ImportError:
        return "unknown", "google-auth not installed"

    try:
        credentials, _ = google.auth.default()
    except Exception as exc:
        return "unknown", f"ADC did not resolve: {type(exc).__name__}"

    email = getattr(credentials, "service_account_email", None)
    if email and email != "default":
        return email, "service account on the credential"

    try:
        credentials.refresh(auth_requests.Request())
        import json as _json
        import urllib.request

        with urllib.request.urlopen(
            "https://oauth2.googleapis.com/tokeninfo?access_token="
            + credentials.token,
            timeout=10,
        ) as response:
            info = _json.load(response)
        found = info.get("email") or info.get("sub")
        if found:
            return found, "tokeninfo"
    except Exception as exc:
        return "unknown", f"token introspection failed: {type(exc).__name__}"
    return "unknown", "credentials carry no identifiable principal"


def preflight() -> int:
    """Print the environment's state, and return an exit code naming whose it is."""
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true"}
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "")
    api_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    from app.agent.gemini import default_model

    print(f"  model                     {default_model()}")
    print(f"  GOOGLE_GENAI_USE_VERTEXAI {use_vertex or '(unset)'}")
    print(f"  GOOGLE_CLOUD_PROJECT      {project or '(unset)'}")
    print(f"  GOOGLE_CLOUD_LOCATION     {location or '(unset)'}")
    print(f"  GEMINI_API_KEY            {'set' if api_key else '(unset)'}")

    if not use_vertex and not api_key:
        print("\nNOT CONFIGURED: neither Vertex nor an API key. Nothing to call.")
        return NOT_CONFIGURED
    if use_vertex and not (project and location):
        print("\nNOT CONFIGURED: Vertex is on but project or location is missing.")
        return NOT_CONFIGURED

    if use_vertex:
        principal, how = resolve_principal()
        print(f"  ADC principal             {principal}  ({how})")
        if principal == "unknown":
            print(
                "\nThe principal could not be resolved, so a pass below proves "
                "nothing about who passed. Treat any success as unverified."
            )
    else:
        print("  ADC principal             n/a (API key, not ADC)")
    return 0


async def probe() -> int:
    """One trivial generation, to separate 'refused' from 'our bug'."""
    from app.agent.gemini import GeminiClient
    from app.agent.llm import LlmRequest
    from app.agent.schemas import PlanProposal

    client = GeminiClient()
    request = LlmRequest(
        model=client.model,
        system="Return an empty plan.",
        payload='{"windows":[],"candidates":[]}',
        output_schema=PlanProposal,
    )
    try:
        response = await client.complete(request)
    except Exception as exc:
        name = type(exc).__name__
        refused = name in {"PermissionDenied", "Forbidden", "Unauthenticated"} or (
            "403" in str(exc) or "PERMISSION_DENIED" in str(exc)
        )
        print(f"\n{'REFUSED' if refused else 'FAILED'}: {name}: {exc}")
        if refused:
            print(
                "Credentials resolved and the API said no. This is an IAM grant "
                "on the principal printed above, not a code change."
            )
        return REFUSED if refused else OUR_BUG
    print(f"\nok: {len(response.text)} chars, stop_reason={response.stop_reason}")
    return 0


async def run(trip_id: uuid.UUID, *, dry_run: bool, model: str | None) -> int:
    import app.db.engine as db
    from app.agent.context import gather
    from app.agent.gemini import GeminiClient, default_model
    from app.agent.prompts import PROMPT_VERSION
    from app.agent.runs import frame, run_pretrip_plan

    now = datetime.now(UTC)
    chosen = model or default_model()

    if dry_run:
        async with db.SessionFactory() as session:
            gathered = await gather(
                session,
                trip_id,
                run_kind="pretrip_plan",
                prompt_version=PROMPT_VERSION,
                now=now,
            )
        ctx = gathered.context
        request = frame(ctx, model=chosen)
        print(
            f"windows={len(ctx.windows)} candidates={len(ctx.candidates)} "
            f"commitments={len(ctx.commitments)} payload={len(request.payload)} chars"
        )
        if ctx.meta.degraded:
            print(f"degraded: {', '.join(ctx.meta.degraded)}")
        if ctx.is_empty_decision_space():
            print("empty decision space: a real run would skip the model entirely")
        return 0

    async with db.SessionFactory() as session:
        outcome = await run_pretrip_plan(
            session,
            trip_id=trip_id,
            client=GeminiClient(model=chosen),
            model=chosen,
            now=now,
        )

    print(f"run {outcome.run_id} {outcome.status}")
    if outcome.status.value == "completed":
        print(f"plan {outcome.plan_id} with {outcome.item_count} items")
        print(f"headline: {outcome.headline or '(none)'}")
        return 0
    print(f"error: {outcome.error}")
    for violation in outcome.violations:
        print(f"  {violation.code} at {violation.path}: {violation.detail}")
    return OUR_BUG


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trip", help="trip_id to plan for")
    parser.add_argument("--model", help="override the configured model")
    parser.add_argument(
        "--check", action="store_true", help="preflight and a trivial call, then exit"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="gather and frame, never call the model"
    )
    args = parser.parse_args()

    load_dotenv()
    print("Environment:")
    state = preflight()

    if args.check:
        return state if state else asyncio.run(probe())
    if not args.trip:
        parser.error("--trip is required unless --check is given")
    if state and not args.dry_run:
        return state

    return asyncio.run(
        run(uuid.UUID(args.trip), dry_run=args.dry_run, model=args.model)
    )


if __name__ == "__main__":
    sys.exit(main())
