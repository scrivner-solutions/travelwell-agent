"""Suite-wide guards that have to hold before any test runs.

Both of these exist because this suite billed real money once. `gather()` asks
the places provider whether an area has been looked at, `default_provider()` is
the live Google client, ADC resolves on a developer box, and
`PLACES_FETCH_ENABLED` defaults to on -- so an ordinary `pytest` run sent live
Places API requests against the project's billing account. Nothing in the code
prevented it. It surfaced only because a test that expected two candidate names
got twenty real Chicago hotels.

The env pin is the policy ceiling; the stub is the mechanism. The stub is the
one that still holds when a test sets the env var itself, which any test
exercising the fetch path has to do.
"""

import os

import pytest

# Set at import time, before app code reads it. `policy.fetch_enabled()` calls
# os.getenv() per call rather than at import, so this pins the ceiling for every
# test in every directory. `load_dotenv()` in tests/api/conftest.py does not
# override an existing variable, so a stray .env cannot lift it.
os.environ["PLACES_FETCH_ENABLED"] = "0"


class _NoLiveProvider:
    """Stands in for the live Google client for the whole suite.

    Raises `AssertionError` and deliberately not `ProviderError`:
    `ensure_area_fresh` catches `ProviderError` and turns it into an outcome, so
    a `ProviderError` raised here would be absorbed into a tidy
    `authoritative=False` and the test would pass while reporting a network call
    it never made. An `AssertionError` is not caught anywhere on that path and
    fails the test that reached for the network.
    """

    name = "google"

    def _refuse(self) -> None:
        raise AssertionError(
            "a test reached the live places provider. Pass an explicit fake "
            "(provider=...) rather than falling through to default_provider()."
        )

    async def geocode(self, query: str):
        self._refuse()

    async def search_nearby(self, query):
        self._refuse()


@pytest.fixture(autouse=True, scope="session")
def _places_provider_is_not_live():
    from app.services.places import registry

    live = registry.providers.get("google")
    registry.register(_NoLiveProvider())
    yield
    if live is not None:
        registry.register(live)
