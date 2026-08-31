"""Places: the provider seam, the cache that fronts it, and the matcher."""

from app.services.places.google import GooglePlaces
from app.services.places.ports import PlacesProvider, Registry

registry = Registry()
registry.register(GooglePlaces())


def default_provider() -> PlacesProvider:
    """The one live provider. A function rather than a constant so a test can
    swap the registry entry without reaching into every call site."""
    return registry.get("google")
