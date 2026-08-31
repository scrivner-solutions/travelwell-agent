"""The one place a provider SDK is imported.

Kept out of `llm.py` on purpose: everything else in `app/agent/` imports the
`LlmClient` protocol, so the package stays importable with no SDK installed and
the whole pipeline is exercisable by `FakeLLM`. Swapping providers is a new
module beside this one plus a wiring change, not a change to any stage.

Auth is ambient. `genai.Client()` with no arguments reads
`GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`
and resolves credentials through ADC, which is the runtime service account on
Cloud Run and a human account locally - deliberately not the same principal, so
a local success proves nothing about staging.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from google import genai
from google.genai import types

from app.agent.llm import LlmRequest, LlmResponse

# Generous on purpose: a structured output that hits the cap is truncated JSON,
# which reads as a schema problem when it is a length problem.
MAX_OUTPUT_TOKENS = 16_000

# Configuration, not a code decision - ADR-003 records the provider as
# provisional, and the run row stores whatever was actually used.
DEFAULT_MODEL = "gemini-2.5-pro"

# Anything not listed is either a refusal or a malformed generation, and both
# are decode failures rather than something a repair turn could fix.
_REFUSALS = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.SPII,
        types.FinishReason.RECITATION,
    }
)


def default_model() -> str:
    return os.getenv("AGENT_MODEL", DEFAULT_MODEL)


def stop_reason_of(finish: types.FinishReason | None) -> str:
    """Provider finish reasons, normalised to the three Decode branches on."""
    if finish is None or finish == types.FinishReason.STOP:
        return "end_turn"
    if finish == types.FinishReason.MAX_TOKENS:
        return "max_tokens"
    if finish in _REFUSALS:
        return "refusal"
    return str(finish)


class GeminiClient:
    """`LlmClient` over `google-genai`. Holds no per-run state."""

    def __init__(self, *, model: str | None = None, client: genai.Client | None = None):
        self.model = model or default_model()
        self._client = client or genai.Client()

    def _config(self, request: LlmRequest) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=request.system,
            response_mime_type="application/json",
            # The full JSON Schema path, not `response_schema`: `$defs` and
            # `$ref` survive it, which is what a nested Pydantic model emits.
            response_json_schema=request.output_schema.model_json_schema(),
            max_output_tokens=MAX_OUTPUT_TOKENS,
            # Gemini spells effort as a thinking level. The mapping lives here
            # rather than in `LlmRequest` so the request stays provider-neutral.
            thinking_config=types.ThinkingConfig(thinking_level=request.effort),
            # No sampling parameters, deliberately. The pipeline does not rely
            # on them and a partial rollback would be worse than none.
        )

    @staticmethod
    def _contents(request: LlmRequest, turns: Sequence[str]) -> list[types.Content]:
        """The payload, then the repair conversation, alternating model/user.

        A repair is a second turn in the same conversation - the model sees its
        own output and a machine-generated list of what was wrong with it.
        """
        contents = [
            types.Content(role="user", parts=[types.Part(text=request.payload)])
        ]
        for index, turn in enumerate(turns):
            role = "model" if index % 2 == 0 else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=turn)]))
        return contents

    async def complete(
        self, request: LlmRequest, *, turns: Sequence[str] = ()
    ) -> LlmResponse:
        response = await self._client.aio.models.generate_content(
            model=request.model,
            contents=self._contents(request, turns),
            config=self._config(request),
        )
        candidate = (response.candidates or [None])[0]
        usage = response.usage_metadata
        return LlmResponse(
            text=response.text or "",
            stop_reason=stop_reason_of(candidate.finish_reason if candidate else None),
            usage={
                "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
                "output_tokens": (usage.candidates_token_count or 0) if usage else 0,
                "thought_tokens": (usage.thoughts_token_count or 0) if usage else 0,
            },
        )
