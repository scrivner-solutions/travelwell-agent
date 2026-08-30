"""Where to send someone when we are not the one booking.

Shared by every provider, so it lives apart from all of them: the simulated
provider needs it for a refusal, the external-link provider needs it as its
entire answer, and neither should import the other.
"""

import urllib.parse


def booking_search_url(place_name: str) -> str:
    """A search for the place, not a booking page.

    Deliberately not a fabricated reservation link. Pointing at a booking
    surface we have no integration with would imply the user can finish there,
    and we do not know that; pointing at the place is true either way.
    """
    query = urllib.parse.urlencode({"api": "1", "query": place_name})
    return f"https://www.google.com/maps/search/?{query}"
