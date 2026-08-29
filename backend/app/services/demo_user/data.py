"""The demo account's contents: one user, eleven trips, and everything under them.

Data only -- no session, no SQL, nothing awaitable. app/services/demo_user/build.py
turns this into rows. Times are trip-relative (`T(day, hour, minute)`, day counted
from the trip's own start date) so the scene never goes stale and each trip's
clock stays in its own timezone.

Every trip earns its place by being the only one that reaches some state: the
roster covers each trip_state, plan_status and item_status the app can render,
so a screen that shows nothing is a bug rather than a gap in the fixture.
"""

from collections.abc import Sequence
from typing import NamedTuple

from app.db.models import (
    ItemKind,
    ItemStatus,
    OptionState,
    PlanStatus,
    SourceKind,
    SourceStatus,
    TripOrigin,
    TripState,
    WindowStatus,
)


class T(NamedTuple):
    """Trip-local wall clock; `day` is an offset from the trip's start date."""

    day: int
    hour: int
    minute: int = 0


# --- identity -------------------------------------------------------------
# Content, not lifecycle: the callers own the email (fixed for the seed script,
# throwaway per tap for /auth/demo) and nothing else.

DISPLAY_NAME = "Demo Traveler"
HOME_TIMEZONE = "America/Los_Angeles"

PREFERENCES = {
    "dietary": ["vegetarian"],
    "activities": ["swim", "running"],
    "amenities": ["pool", "treadmill"],
    "memberships": ["ymca_reciprocity", "hotel_gym"],
    "price_level_max": 2,
    "day_pass_budget_cents": 2000,
    "session_min_minutes": 45,
    "session_max_minutes": 90,
    "preferred_times": ["mornings"],
    "allow_calendar_write": True,
    "allow_auto_book": False,
    "watch_schedule": True,
}


class SourceSpec(NamedTuple):
    key: str
    kind: SourceKind
    status: SourceStatus
    scopes: list[str]
    synced_minutes_ago: int


SOURCES = [
    SourceSpec(
        key="calendar",
        kind=SourceKind.google_calendar,
        status=SourceStatus.connected,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        synced_minutes_ago=4,
    ),
    # Trip evidence cites Email as a source; this is its grant.
    SourceSpec(
        key="email",
        kind=SourceKind.gmail,
        status=SourceStatus.connected,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        synced_minutes_ago=60,
    ),
]


# --- places ---------------------------------------------------------------
# A shared cache keyed by provider_ref, not user-scoped: build.py upserts these
# so two demo accounts reference the same rows, exactly as the real cache would.

WEEKDAY_HOURS = {
    "mon": [360, 1320], "tue": [360, 1320], "wed": [360, 1320],
    "thu": [360, 1320], "fri": [360, 1290], "sat": [420, 1200],
    "sun": [420, 1200],
}
DINNER_HOURS = {
    "mon": [660, 1320], "tue": [660, 1320], "wed": [660, 1320],
    "thu": [660, 1350], "fri": [660, 1380], "sat": [600, 1380],
    "sun": [600, 1260],
}


class PlaceSpec(NamedTuple):
    key: str
    provider_ref: str
    kind: str
    name: str
    summary: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    price_level: int | None = None
    day_pass_cents: int | None = None
    amenities: Sequence[str] = ()
    hours: dict | None = None
    photo_url: str | None = None
    reservable_via: str | None = None


PLACES = [
    # Chicago
    PlaceSpec(
        key="gwen", provider_ref="gmp_chi_gwen", kind="lodging", name="The Gwen",
        summary="Michigan Avenue · 4 star", address="521 N Rush St, Chicago, IL 60611",
        lat=41.8924, lng=-87.6252, price_level=3, amenities=["gym", "wifi"],
        photo_url="https://images.travelwell.dev/places/gwen.jpg",
    ),
    PlaceSpec(
        key="ymca_chi", provider_ref="gmp_chi_ymca", kind="workout",
        name="YMCA", summary="Pool + treadmill · 75 min",
        address="1030 W Van Buren St, Chicago, IL 60607",
        lat=41.8763, lng=-87.6534, day_pass_cents=1500,
        amenities=["pool", "treadmill", "sauna"], hours=WEEKDAY_HOURS,
        photo_url="https://images.travelwell.dev/places/ymca-chi.jpg",
    ),
    PlaceSpec(
        key="gwen_gym", provider_ref="gmp_chi_gwen_gym", kind="workout",
        name="Hotel fitness room", summary="Treadmill + weights · 40 min",
        address="521 N Rush St, Chicago, IL 60611", lat=41.8924, lng=-87.6252,
        day_pass_cents=0, amenities=["treadmill", "weights"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="cac", provider_ref="gmp_chi_cac", kind="workout",
        name="Chicago Athletic Club", summary="Lap pool · 60 min",
        address="12 S Michigan Ave, Chicago, IL 60603", lat=41.8814, lng=-87.6246,
        day_pass_cents=3500, amenities=["pool", "sauna"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="beatrix", provider_ref="gmp_chi_beatrix", kind="food",
        name="Beatrix", summary="Healthy American · $$",
        address="519 N Clark St, Chicago, IL 60654", lat=41.8912, lng=-87.6312,
        price_level=2, amenities=["vegetarian", "vegan"], hours=DINNER_HOURS,
        photo_url="https://images.travelwell.dev/places/beatrix.jpg",
        reservable_via="opentable",
    ),
    PlaceSpec(
        key="aba", provider_ref="gmp_chi_aba", kind="food", name="Aba",
        summary="Mediterranean · $$$", address="302 N Green St, Chicago, IL 60607",
        lat=41.8871, lng=-87.6487, price_level=3, amenities=["vegetarian"],
        hours=DINNER_HOURS, reservable_via="opentable",
    ),
    PlaceSpec(
        key="gwen_rest", provider_ref="gmp_chi_gwen_rest", kind="food",
        name="Hotel restaurant", summary="American · $$$",
        address="521 N Rush St, Chicago, IL 60611", lat=41.8924, lng=-87.6252,
        price_level=3, hours=DINNER_HOURS,
    ),
    PlaceSpec(
        key="lakefront", provider_ref="gmp_chi_lakefront", kind="outdoor",
        name="Lakefront Trail", summary="40-minute run · flat loop",
        address="Lake Shore Dr, Chicago, IL", lat=41.8925, lng=-87.6126,
        day_pass_cents=0, amenities=["running", "outdoor"],
    ),
    PlaceSpec(
        key="riverwalk", provider_ref="gmp_chi_riverwalk", kind="outdoor",
        name="Riverwalk loop", summary="30-minute run",
        address="Chicago Riverwalk, Chicago, IL", lat=41.8879, lng=-87.6265,
        day_pass_cents=0, amenities=["running", "outdoor"],
    ),
    # Denver
    PlaceSpec(
        key="crawford", provider_ref="gmp_den_crawford", kind="lodging",
        name="The Crawford Hotel", summary="Union Station · 4 star",
        address="1701 Wynkoop St, Denver, CO 80202", lat=39.7527, lng=-105.0000,
        price_level=3, amenities=["gym", "wifi"],
    ),
    PlaceSpec(
        key="rally", provider_ref="gmp_den_rally", kind="workout",
        name="Rally Sport", summary="Lap pool + weights · 60 min",
        address="2727 29th St, Denver, CO 80301", lat=40.0210, lng=-105.2540,
        day_pass_cents=2000, amenities=["pool", "weights"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="cherry_creek", provider_ref="gmp_den_cherry", kind="outdoor",
        name="Cherry Creek Trail", summary="45-minute run · paved",
        address="Cherry Creek Trail, Denver, CO", lat=39.7420, lng=-104.9830,
        day_pass_cents=0, amenities=["running", "outdoor"],
    ),
    PlaceSpec(
        key="root_down", provider_ref="gmp_den_rootdown", kind="food",
        name="Root Down", summary="Seasonal vegetarian · $$",
        address="1600 W 33rd Ave, Denver, CO 80211", lat=39.7638, lng=-105.0130,
        price_level=2, amenities=["vegetarian", "vegan"], hours=DINNER_HOURS,
        reservable_via="opentable",
    ),
    PlaceSpec(
        key="linger", provider_ref="gmp_den_linger", kind="food", name="Linger",
        summary="Street food · $$$", address="2030 W 30th Ave, Denver, CO 80211",
        lat=39.7597, lng=-105.0126, price_level=3, hours=DINNER_HOURS,
        reservable_via="opentable",
    ),
    # New York
    PlaceSpec(
        key="ace_nyc", provider_ref="gmp_nyc_ace", kind="lodging",
        name="Ace Hotel New York", summary="NoMad · 4 star",
        address="20 W 29th St, New York, NY 10001", lat=40.7457, lng=-73.9884,
        price_level=3, amenities=["gym", "wifi"],
    ),
    PlaceSpec(
        key="asphalt_green", provider_ref="gmp_nyc_asphalt", kind="workout",
        name="Asphalt Green", summary="50m pool · 60 min",
        address="555 E 90th St, New York, NY 10128", lat=40.7810, lng=-73.9440,
        day_pass_cents=2500, amenities=["pool"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="chelsea_piers", provider_ref="gmp_nyc_chelsea", kind="workout",
        name="Chelsea Piers Fitness", summary="Pool + track · 75 min",
        address="Pier 60, New York, NY 10011", lat=40.7467, lng=-74.0086,
        day_pass_cents=5000, amenities=["pool", "track"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="hudson_greenway", provider_ref="gmp_nyc_hudson", kind="outdoor",
        name="Hudson River Greenway", summary="35-minute run · riverside",
        address="Hudson River Park, New York, NY", lat=40.7480, lng=-74.0100,
        day_pass_cents=0, amenities=["running", "outdoor"],
    ),
    PlaceSpec(
        key="dirt_candy", provider_ref="gmp_nyc_dirtcandy", kind="food",
        name="Dirt Candy", summary="Vegetable tasting · $$",
        address="86 Allen St, New York, NY 10002", lat=40.7185, lng=-73.9903,
        price_level=2, amenities=["vegetarian", "vegan"], hours=DINNER_HOURS,
        reservable_via="opentable",
    ),
    PlaceSpec(
        key="gramercy", provider_ref="gmp_nyc_gramercy", kind="food",
        name="Gramercy Tavern", summary="New American · $$$$",
        address="42 E 20th St, New York, NY 10003", lat=40.7386, lng=-73.9883,
        price_level=4, hours=DINNER_HOURS, reservable_via="opentable",
    ),
    # Seattle
    PlaceSpec(
        key="thompson_sea", provider_ref="gmp_sea_thompson", kind="lodging",
        name="Thompson Seattle", summary="Pike Place · 4 star",
        address="110 Stewart St, Seattle, WA 98101", lat=47.6094, lng=-122.3400,
        price_level=3, amenities=["gym", "wifi"],
    ),
    PlaceSpec(
        key="medgar_evers", provider_ref="gmp_sea_medgar", kind="workout",
        name="Medgar Evers Pool", summary="Lap swim · 60 min",
        address="500 23rd Ave, Seattle, WA 98122", lat=47.6055, lng=-122.3020,
        day_pass_cents=800, amenities=["pool"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="green_lake", provider_ref="gmp_sea_greenlake", kind="outdoor",
        name="Green Lake Loop", summary="45-minute run · 2.8 mile loop",
        address="Green Lake Park, Seattle, WA", lat=47.6806, lng=-122.3400,
        day_pass_cents=0, amenities=["running", "outdoor"],
    ),
    PlaceSpec(
        key="cafe_flora", provider_ref="gmp_sea_flora", kind="food",
        name="Cafe Flora", summary="Vegetarian · $$",
        address="2901 E Madison St, Seattle, WA 98112", lat=47.6265, lng=-122.2920,
        price_level=2, amenities=["vegetarian", "vegan"], hours=DINNER_HOURS,
        reservable_via="opentable",
    ),
    # Vancouver
    PlaceSpec(
        key="opus_van", provider_ref="gmp_van_opus", kind="lodging",
        name="Opus Vancouver", summary="Yaletown · 4 star",
        address="322 Davie St, Vancouver, BC V6B 5Z6", lat=49.2757, lng=-123.1220,
        price_level=3, amenities=["gym", "wifi"],
    ),
    PlaceSpec(
        key="seawall", provider_ref="gmp_van_seawall", kind="outdoor",
        name="Stanley Park Seawall", summary="50-minute run · waterfront",
        address="Stanley Park, Vancouver, BC", lat=49.3020, lng=-123.1440,
        day_pass_cents=0, amenities=["running", "outdoor"],
    ),
    PlaceSpec(
        key="acorn", provider_ref="gmp_van_acorn", kind="food", name="The Acorn",
        summary="Vegetarian · $$", address="3995 Main St, Vancouver, BC V5V 3P3",
        lat=49.2487, lng=-123.1010, price_level=2,
        amenities=["vegetarian", "vegan"], hours=DINNER_HOURS,
        reservable_via="opentable",
    ),
    # London
    PlaceSpec(
        key="hoxton_ldn", provider_ref="gmp_ldn_hoxton", kind="lodging",
        name="The Hoxton, Holborn", summary="Holborn · 4 star",
        address="199-206 High Holborn, London WC1V 7BD", lat=51.5178, lng=-0.1200,
        price_level=3, amenities=["gym", "wifi"],
    ),
    PlaceSpec(
        key="oasis_ldn", provider_ref="gmp_ldn_oasis", kind="workout",
        name="Oasis Sports Centre", summary="Heated outdoor pool · 45 min",
        address="32 Endell St, London WC2H 9AG", lat=51.5147, lng=-0.1256,
        day_pass_cents=700, amenities=["pool"], hours=WEEKDAY_HOURS,
    ),
    PlaceSpec(
        key="mildreds", provider_ref="gmp_ldn_mildreds", kind="food",
        name="Mildreds Soho", summary="Vegetarian · $$",
        address="45 Lexington St, London W1F 9AN", lat=51.5128, lng=-0.1370,
        price_level=2, amenities=["vegetarian", "vegan"], hours=DINNER_HOURS,
    ),
    # Portland
    PlaceSpec(
        key="jupiter_pdx", provider_ref="gmp_pdx_jupiter", kind="lodging",
        name="Jupiter NEXT", summary="Central Eastside · 3 star",
        address="900 E Burnside St, Portland, OR 97214", lat=45.5230, lng=-122.6580,
        price_level=2, amenities=["gym", "wifi"],
    ),
]


# --- trip content ---------------------------------------------------------


class EvidenceSpec(NamedTuple):
    kind: str
    source_label: str
    summary: str
    detail: str
    source_ref: str


class CalEventSpec(NamedTuple):
    key: str
    title: str
    starts: T
    ends: T
    location: str | None = None
    status: str = "confirmed"


class BoundSpec(NamedTuple):
    kind: str
    tag: str
    title: str
    detail: str
    source_label: str


class WindowSpec(NamedTuple):
    key: str
    local_day: int
    starts: T
    ends: T
    label: str
    gap_explanation: str
    bounds: list[BoundSpec]
    status: WindowStatus = WindowStatus.open


class OptionSpec(NamedTuple):
    state: OptionState
    place: str
    display_name: str
    display_summary: str | None = None
    reason: str | None = None
    rejection_reason: str | None = None
    distance_minutes: int | None = None
    duration_minutes: int | None = None
    matched_preferences: Sequence[str] = ()


class ItemSpec(NamedTuple):
    key: str
    kind: ItemKind
    status: ItemStatus
    starts: T
    ends: T
    options: list[OptionSpec]
    window: str | None = None
    needs_reservation: bool = False
    calendar_event_ref: str | None = None


class PlanSpec(NamedTuple):
    version: int
    status: PlanStatus
    headline: str
    provenance_summary: str
    run: str
    items: list[ItemSpec]


class EventSpec(NamedTuple):
    key: str
    kind: str
    occurred: T
    payload: dict
    disposition: str = "accepted"


class RunSpec(NamedTuple):
    key: str
    kind: str
    status: str
    started: T
    context_snapshot: dict
    trigger_event: str | None = None
    finished: T | None = None
    result: dict | None = None
    model: str = "claude-sonnet-5"
    error: str | None = None


class ActionSpec(NamedTuple):
    key: str
    type: str
    status: str
    proposed: T
    proposed_payload: dict
    subject_item: str | None = None
    approval_required: bool = True
    approved: T | None = None
    executed: T | None = None
    execution_result: dict | None = None
    verification: dict | None = None


class ReservationSpec(NamedTuple):
    provider: str
    status: str
    slot: T
    item: str | None = None
    place: str | None = None
    party_size: int = 1
    confirmation_code: str | None = None
    failure_reason: str | None = None
    external_url: str | None = None


class NotificationSpec(NamedTuple):
    kind: str
    title: str
    created: T
    body: str | None = None
    cta: dict | None = None
    status: str = "sent"
    run: str | None = None
    sent: T | None = None
    opened: T | None = None


class TripSpec(NamedTuple):
    key: str
    city: str
    region: str
    timezone: str
    lat: float
    lng: float
    starts_in_days: int
    nights: int
    state: TripState
    origin: TripOrigin
    label: str | None = None
    hotel: str | None = None
    detection_confidence: float | None = None
    evidence: Sequence[EvidenceSpec] = ()
    calendar_events: Sequence[CalEventSpec] = ()
    windows: Sequence[WindowSpec] = ()
    events: Sequence[EventSpec] = ()
    runs: Sequence[RunSpec] = ()
    plans: Sequence[PlanSpec] = ()
    actions: Sequence[ActionSpec] = ()
    reservations: Sequence[ReservationSpec] = ()
    notifications: Sequence[NotificationSpec] = ()


sel, alt, rej = OptionState.selected, OptionState.alternative, OptionState.rejected


# --- Chicago: mid-trip, day 2 of 4. The Today screen's richest state. -------

CHICAGO = TripSpec(
    key="chicago",
    city="Chicago", region="IL", timezone="America/Chicago",
    lat=41.8871, lng=-87.6270,
    starts_in_days=-1, nights=3,
    label="Conference trip",
    state=TripState.active,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.93,
    hotel="gwen",
    evidence=[
        EvidenceSpec("flight_event", "Calendar", "UA 1142 · SFO to ORD",
                     "Lands 9:40 AM · confirmed", "cal_evt_ua1142"),
        EvidenceSpec("hotel_email", "Email", "The Gwen",
                     "521 N Rush St · 3 nights", "msg_gwen_conf"),
        EvidenceSpec("conference_event", "Calendar", "TechConf Chicago",
                     "McCormick Place · all-day blocks", "cal_evt_techconf"),
    ],
    calendar_events=[
        CalEventSpec("chi_conf", "Conference", T(1, 8), T(1, 12), "McCormick Place"),
        CalEventSpec("chi_lunch", "Lunch with the team", T(1, 12), T(1, 13, 30)),
        CalEventSpec("chi_workshop", "Workshop", T(1, 14), T(1, 17, 30), "Room 4B"),
        CalEventSpec("chi_keynote", "Keynote", T(2, 9), T(2, 10, 30), "Main hall"),
        CalEventSpec("chi_dinner", "Team dinner", T(2, 19), T(2, 21),
                     "Booked by the client"),
    ],
    windows=[
        WindowSpec(
            key="chi_evening", local_day=1, starts=T(1, 17, 30), ends=T(1, 19),
            label="90 minutes free",
            gap_explanation="Between your workshop and dinner, 5:30 to 7:00.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Workshop, Room 4B",
                          "Ends 5:30 PM", "Calendar"),
                BoundSpec("plan_item", "PLAN", "Dinner you kept",
                          "Starts 7:30 PM", "This plan"),
            ],
            status=WindowStatus.filled,
        ),
        WindowSpec(
            key="chi_morning", local_day=2, starts=T(2, 6, 45), ends=T(2, 8),
            label="75 minutes before the keynote",
            gap_explanation="Your first commitment is the 9:00 keynote.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Conference keynote",
                          "Starts 9:00 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "The Gwen",
                          "Trail is 12 minutes away", "Email"),
            ],
            status=WindowStatus.filled,
        ),
        # An opening that came and went unused: the Today screen filters it out.
        WindowSpec(
            key="chi_expired", local_day=0, starts=T(0, 15), ends=T(0, 16, 30),
            label="90 minutes after landing",
            gap_explanation="Between your flight and the welcome reception.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "UA 1142 arrival",
                          "Lands 9:40 AM", "Calendar"),
                BoundSpec("calendar_event", "CAL", "Welcome reception",
                          "Starts 6:00 PM", "Calendar"),
            ],
            status=WindowStatus.expired,
        ),
    ],
    events=[
        EventSpec("chi_activation", "scheduled_activation", T(-7, 0, 2),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
        EventSpec("chi_daily", "scheduled_daily", T(1, 6),
                  {"reason": "morning check-in"}),
    ],
    runs=[
        RunSpec(
            key="chi_plan", kind="pretrip_plan", status="completed",
            trigger_event="chi_activation",
            started=T(-7, 0, 2), finished=T(-7, 0, 4),
            context_snapshot={
                "trip": {"city": "Chicago", "nights": 3},
                "calendar_events_read": 11,
                "windows_found": 3,
                "preferences": {"dietary": ["vegetarian"], "activities": ["swim", "running"]},
            },
            result={"items_proposed": 3, "windows_filled": 2, "headline": "Room for 3 workouts and a dinner"},
        ),
        RunSpec(
            key="chi_checkin", kind="daily_checkin", status="completed",
            trigger_event="chi_daily",
            started=T(1, 6), finished=T(1, 6, 1),
            context_snapshot={"day": 2, "items_today": 2},
            result={"changes": 0, "message": "No schedule changes overnight"},
        ),
    ],
    plans=[
        PlanSpec(
            version=1, status=PlanStatus.accepted, run="chi_plan",
            headline="Room for 3 workouts and a dinner",
            provenance_summary=(
                "Prepared a week out · read 11 calendar events · found 3 open windows"
            ),
            items=[
                ItemSpec(
                    key="chi_ymca", kind=ItemKind.activity,
                    status=ItemStatus.confirmed, window="chi_evening",
                    starts=T(1, 17, 30), ends=T(1, 18, 45),
                    calendar_event_ref="cal_evt_twl_ymca",
                    options=[
                        OptionSpec(sel, "ymca_chi", "YMCA", "Pool + treadmill · 75 min",
                                   reason="Fits your 90-minute opening",
                                   distance_minutes=7, duration_minutes=75,
                                   matched_preferences=["Swim", "45-90 min"]),
                        OptionSpec(alt, "gwen_gym", "Hotel fitness room",
                                   "Treadmill + weights · 40 min",
                                   reason="No travel time at all",
                                   distance_minutes=0, duration_minutes=40),
                        OptionSpec(rej, "cac", "Chicago Athletic Club",
                                   "Lap pool · 60 min",
                                   rejection_reason=(
                                       "11 minutes each way left you tight for a 7:30 table"
                                   ),
                                   distance_minutes=11, duration_minutes=60),
                    ],
                ),
                ItemSpec(
                    key="chi_dinner", kind=ItemKind.meal,
                    status=ItemStatus.confirmed, needs_reservation=True,
                    starts=T(1, 19, 30), ends=T(1, 21),
                    calendar_event_ref="cal_evt_twl_beatrix",
                    options=[
                        OptionSpec(sel, "beatrix", "Beatrix", "Healthy American · $$",
                                   reason="Matches your vegetarian preference",
                                   distance_minutes=5,
                                   matched_preferences=["Vegetarian", "$$ or less"]),
                        OptionSpec(rej, "aba", "Aba", "Mediterranean · $$$",
                                   rejection_reason="$$$, above the budget you set",
                                   distance_minutes=9),
                        OptionSpec(rej, "gwen_rest", "Hotel restaurant",
                                   rejection_reason="No vegetarian main after 7 PM",
                                   distance_minutes=0),
                    ],
                ),
                ItemSpec(
                    key="chi_run", kind=ItemKind.activity,
                    status=ItemStatus.planned, window="chi_morning",
                    starts=T(2, 6, 45), ends=T(2, 7, 30),
                    options=[
                        OptionSpec(sel, "lakefront", "Lakefront Trail",
                                   "40-minute run · flat loop",
                                   reason="Back with time to shower",
                                   distance_minutes=12, duration_minutes=40,
                                   matched_preferences=["Running", "Mornings"]),
                        OptionSpec(alt, "riverwalk", "Riverwalk loop",
                                   "30-minute run",
                                   reason="Closer, if you wake up late",
                                   distance_minutes=4, duration_minutes=30),
                        OptionSpec(rej, "gwen_gym", "Hotel fitness room",
                                   rejection_reason="You were indoors the day before",
                                   distance_minutes=0),
                    ],
                ),
                # Terminal states the timeline must hide.
                ItemSpec(
                    key="chi_skipped", kind=ItemKind.activity,
                    status=ItemStatus.skipped, starts=T(1, 12, 15), ends=T(1, 13),
                    options=[
                        OptionSpec(sel, "gwen_gym", "Hotel fitness room",
                                   "Quick 30 minutes", reason="A gap before your workshop",
                                   distance_minutes=0, duration_minutes=30),
                    ],
                ),
            ],
        ),
    ],
    actions=[
        ActionSpec(
            key="chi_res", type="make_reservation", status="completed",
            subject_item="chi_dinner", approval_required=True,
            proposed=T(-7, 0, 4), approved=T(-6, 9, 12), executed=T(-6, 9, 13),
            proposed_payload={"provider": "opentable", "place": "Beatrix",
                              "party_size": 1, "slot": "day 1, 7:30 PM"},
            execution_result={"confirmation_code": "#4F21B", "status": "confirmed"},
            verification={"re_read_at": "day -6 9:14", "provider_status": "confirmed"},
        ),
        ActionSpec(
            key="chi_cal_ymca", type="create_calendar_event", status="completed",
            subject_item="chi_ymca", approval_required=False,
            proposed=T(-6, 9, 13), approved=T(-6, 9, 13), executed=T(-6, 9, 14),
            proposed_payload={"title": "YMCA", "starts": "day 1, 5:30 PM",
                              "ends": "day 1, 6:45 PM"},
            execution_result={"event_id": "cal_evt_twl_ymca", "status": "created"},
            verification={"re_read_at": "day -6 9:15", "found": True},
        ),
        ActionSpec(
            key="chi_cal_dinner", type="create_calendar_event", status="completed",
            subject_item="chi_dinner", approval_required=False,
            proposed=T(-6, 9, 13), approved=T(-6, 9, 13), executed=T(-6, 9, 14),
            proposed_payload={"title": "Dinner · Beatrix", "starts": "day 1, 7:30 PM",
                              "ends": "day 1, 9:00 PM"},
            execution_result={"event_id": "cal_evt_twl_beatrix", "status": "created"},
            verification={"re_read_at": "day -6 9:15", "found": True},
        ),
    ],
    reservations=[
        ReservationSpec(
            provider="opentable", status="confirmed", item="chi_dinner",
            place="beatrix", slot=T(1, 19, 30), party_size=1,
            confirmation_code="#4F21B",
            external_url="https://www.opentable.com/r/beatrix-chicago",
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="plan_ready", title="Your Chicago plan is ready",
            body="Three openings filled, one dinner held.",
            cta={"label": "Review plan", "deep_link": "/trip?trip=chicago"},
            run="chi_plan", status="opened",
            created=T(-7, 0, 4), sent=T(-7, 0, 4), opened=T(-6, 9, 10),
        ),
    ],
)


# --- Portland: the agent is mid-run, plan still a draft. -------------------

PORTLAND = TripSpec(
    key="portland",
    city="Portland", region="OR", timezone="America/Los_Angeles",
    lat=45.5152, lng=-122.6784,
    starts_in_days=5, nights=3,
    label="Team offsite",
    state=TripState.preparing,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.88,
    hotel="jupiter_pdx",
    evidence=[
        EvidenceSpec("flight_event", "Calendar", "AS 512 · SFO to PDX",
                     "Departs 7:15 AM · confirmed", "cal_evt_as512"),
        EvidenceSpec("hotel_email", "Email", "Jupiter NEXT",
                     "900 E Burnside St · 3 nights", "msg_jupiter_conf"),
    ],
    calendar_events=[
        CalEventSpec("pdx_offsite", "Team offsite", T(1, 9), T(1, 17),
                     "Jupiter NEXT, Ballroom"),
        CalEventSpec("pdx_retro", "Quarterly retro", T(2, 10), T(2, 12),
                     "Jupiter NEXT, Ballroom"),
    ],
    events=[
        EventSpec("pdx_activation", "scheduled_activation", T(-2, 0, 1),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
    ],
    runs=[
        # Still running: this is what `Preparing...` means on the trip row.
        RunSpec(
            key="pdx_plan", kind="pretrip_plan", status="running",
            trigger_event="pdx_activation", started=T(-2, 0, 1),
            context_snapshot={
                "trip": {"city": "Portland", "nights": 3},
                "calendar_events_read": 6,
                "windows_found": 2,
            },
        ),
    ],
    plans=[
        # Draft: excluded from the trip rollup on purpose, so a half-built plan
        # never counts as work waiting on the user.
        PlanSpec(
            version=1, status=PlanStatus.draft, run="pdx_plan",
            headline="Two openings around the offsite",
            provenance_summary="Reading your calendar · 6 events so far",
            items=[
                ItemSpec(
                    key="pdx_draft_run", kind=ItemKind.activity,
                    status=ItemStatus.suggested, starts=T(1, 6, 30), ends=T(1, 7, 15),
                    options=[
                        OptionSpec(sel, "jupiter_pdx", "Hotel fitness room",
                                   "Treadmill · 45 min",
                                   reason="Before the 9:00 offsite",
                                   distance_minutes=0, duration_minutes=45,
                                   matched_preferences=["Mornings"]),
                    ],
                ),
            ],
        ),
    ],
)


# --- Denver: booking in flight, and two different gates open at once. ------

DENVER = TripSpec(
    key="denver",
    city="Denver", region="CO", timezone="America/Denver",
    lat=39.7392, lng=-104.9903,
    starts_in_days=12, nights=3,
    label="Customer onsite",
    state=TripState.confirmed,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.91,
    hotel="crawford",
    evidence=[
        EvidenceSpec("flight_event", "Calendar", "UA 763 · SFO to DEN",
                     "Departs 8:05 AM · confirmed", "cal_evt_ua763"),
        EvidenceSpec("hotel_email", "Email", "The Crawford Hotel",
                     "1701 Wynkoop St · 3 nights", "msg_crawford_conf"),
    ],
    calendar_events=[
        CalEventSpec("den_onsite", "Customer onsite", T(1, 9), T(1, 16),
                     "Union Station office"),
        CalEventSpec("den_workshop", "Architecture workshop", T(2, 10), T(2, 15),
                     "Union Station office"),
        CalEventSpec("den_flight_home", "UA 764 · DEN to SFO", T(3, 17), T(3, 19)),
    ],
    windows=[
        WindowSpec(
            key="den_morning", local_day=1, starts=T(1, 6, 30), ends=T(1, 8, 15),
            label="105 minutes before the onsite",
            gap_explanation="Your first commitment is the 9:00 onsite.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Customer onsite",
                          "Starts 9:00 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "The Crawford Hotel",
                          "Trail is 6 minutes away", "Email"),
            ],
            status=WindowStatus.filled,
        ),
        WindowSpec(
            key="den_evening", local_day=2, starts=T(2, 17), ends=T(2, 19),
            label="2 hours free",
            gap_explanation="After the workshop, nothing until tomorrow.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Architecture workshop",
                          "Ends 3:00 PM", "Calendar"),
                BoundSpec("itinerary", "FLT", "UA 764 home",
                          "Departs tomorrow 5:00 PM", "Calendar"),
            ],
        ),
    ],
    events=[
        EventSpec("den_activation", "scheduled_activation", T(-7, 0, 3),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
    ],
    runs=[
        RunSpec(
            key="den_plan", kind="pretrip_plan", status="completed",
            trigger_event="den_activation",
            started=T(-7, 0, 3), finished=T(-7, 0, 5),
            context_snapshot={"trip": {"city": "Denver", "nights": 3},
                              "calendar_events_read": 7, "windows_found": 2},
            result={"items_proposed": 3, "windows_filled": 2},
        ),
        RunSpec(
            key="den_booking", kind="reservation_flow", status="running",
            started=T(-1, 14, 20),
            context_snapshot={"item": "Root Down", "slot": "day 2, 7:00 PM"},
        ),
    ],
    plans=[
        PlanSpec(
            version=1, status=PlanStatus.partially_accepted, run="den_plan",
            headline="A morning run and a table held",
            provenance_summary=(
                "Prepared a week out · read 7 calendar events · found 2 open windows"
            ),
            items=[
                ItemSpec(
                    key="den_run", kind=ItemKind.activity,
                    status=ItemStatus.planned, window="den_morning",
                    starts=T(1, 6, 30), ends=T(1, 7, 15),
                    options=[
                        OptionSpec(sel, "cherry_creek", "Cherry Creek Trail",
                                   "45-minute run · paved",
                                   reason="Six minutes from the hotel door",
                                   distance_minutes=6, duration_minutes=45,
                                   matched_preferences=["Running", "Mornings"]),
                        OptionSpec(alt, "rally", "Rally Sport",
                                   "Lap pool + weights · 60 min",
                                   reason="If the weather turns",
                                   distance_minutes=14, duration_minutes=60),
                    ],
                ),
                # Mid-booking: the `Booking...` badge on the trip row.
                ItemSpec(
                    key="den_dinner", kind=ItemKind.meal,
                    status=ItemStatus.working, needs_reservation=True,
                    starts=T(2, 19), ends=T(2, 20, 30),
                    options=[
                        OptionSpec(sel, "root_down", "Root Down",
                                   "Seasonal vegetarian · $$",
                                   reason="Matches your vegetarian preference",
                                   distance_minutes=8,
                                   matched_preferences=["Vegetarian", "$$ or less"]),
                        OptionSpec(rej, "linger", "Linger", "Street food · $$$",
                                   rejection_reason="$$$, above the budget you set",
                                   distance_minutes=9),
                    ],
                ),
                # Waiting on a decision: the plan half of the mixed needs-you.
                ItemSpec(
                    key="den_swim", kind=ItemKind.activity,
                    status=ItemStatus.awaiting_user, window="den_evening",
                    starts=T(2, 17, 15), ends=T(2, 18, 15),
                    options=[
                        OptionSpec(sel, "rally", "Rally Sport",
                                   "Lap pool + weights · 60 min",
                                   reason="A pool, though it is a 14-minute ride",
                                   distance_minutes=14, duration_minutes=60,
                                   matched_preferences=["Swim"]),
                        OptionSpec(alt, "crawford", "Hotel fitness room",
                                   "Treadmill · 40 min",
                                   reason="No travel time, but no pool",
                                   distance_minutes=0, duration_minutes=40),
                    ],
                ),
            ],
        ),
    ],
    actions=[
        ActionSpec(
            key="den_res", type="make_reservation", status="executing",
            subject_item="den_dinner", approval_required=False,
            proposed=T(-1, 14, 20), approved=T(-1, 14, 20),
            proposed_payload={"provider": "opentable", "place": "Root Down",
                              "party_size": 1, "slot": "day 2, 7:00 PM"},
        ),
        # The approval half of the mixed needs-you.
        ActionSpec(
            key="den_cal", type="create_calendar_event", status="proposed",
            subject_item="den_run", approval_required=True, proposed=T(-1, 14, 25),
            proposed_payload={"title": "Cherry Creek Trail run",
                              "starts": "day 1, 6:30 AM", "ends": "day 1, 7:15 AM"},
        ),
    ],
    reservations=[
        ReservationSpec(
            provider="opentable", status="holding", item="den_dinner",
            place="root_down", slot=T(2, 19), party_size=1,
            external_url="https://www.opentable.com/r/root-down-denver",
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="plan_ready", title="Your Denver plan is ready",
            body="Two openings filled. One needs your call.",
            cta={"label": "Review plan", "deep_link": "/trip?trip=denver"},
            run="den_plan", status="sent",
            created=T(-7, 0, 5), sent=T(-7, 0, 5),
        ),
    ],
)


# --- New York: a whole plan waiting on the user. Nothing else is open. -----

NEW_YORK = TripSpec(
    key="newyork",
    city="New York", region="NY", timezone="America/New_York",
    lat=40.7128, lng=-74.0060,
    starts_in_days=21, nights=3,
    label="Client visit",
    # Hand-entered, so detection_confidence stays null: this trip was never
    # detected, and filling that column in would be fiction.
    state=TripState.confirmed,
    origin=TripOrigin.manual,
    hotel="ace_nyc",
    calendar_events=[
        CalEventSpec("nyc_client", "Client review", T(1, 10), T(1, 15),
                     "Midtown office"),
        CalEventSpec("nyc_dinner", "Client dinner", T(1, 19), T(1, 21, 30),
                     "Booked by the client"),
    ],
    windows=[
        WindowSpec(
            key="nyc_morning", local_day=1, starts=T(1, 6, 30), ends=T(1, 8, 30),
            label="2 hours before the review",
            gap_explanation="Your first commitment is the 10:00 client review.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Client review",
                          "Starts 10:00 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "Ace Hotel New York",
                          "Greenway is 9 minutes away", "Manual"),
            ],
        ),
        WindowSpec(
            key="nyc_afternoon", local_day=2, starts=T(2, 15), ends=T(2, 17, 30),
            label="150 minutes free",
            gap_explanation="Nothing on your calendar after 3:00.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Client review",
                          "Ended yesterday", "Calendar"),
                BoundSpec("itinerary", "HTL", "Ace Hotel New York",
                          "Check-out is tomorrow", "Manual"),
            ],
        ),
    ],
    events=[
        EventSpec("nyc_activation", "scheduled_activation", T(-7, 0, 1),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
    ],
    runs=[
        RunSpec(
            key="nyc_plan", kind="pretrip_plan", status="completed",
            trigger_event="nyc_activation",
            started=T(-7, 0, 1), finished=T(-7, 0, 3),
            context_snapshot={"trip": {"city": "New York", "nights": 3},
                              "calendar_events_read": 4, "windows_found": 2},
            result={"items_proposed": 3, "windows_filled": 2},
        ),
    ],
    plans=[
        PlanSpec(
            version=1, status=PlanStatus.proposed, run="nyc_plan",
            headline="Three openings, all yours to pick",
            provenance_summary=(
                "Prepared a week out · read 4 calendar events · found 2 open windows"
            ),
            items=[
                ItemSpec(
                    key="nyc_swim", kind=ItemKind.activity,
                    status=ItemStatus.awaiting_user, window="nyc_morning",
                    starts=T(1, 6, 45), ends=T(1, 7, 45),
                    options=[
                        OptionSpec(sel, "asphalt_green", "Asphalt Green",
                                   "50m pool · 60 min",
                                   reason="The only 50-metre pool near you",
                                   distance_minutes=18, duration_minutes=60,
                                   matched_preferences=["Swim", "Mornings"]),
                        OptionSpec(alt, "chelsea_piers", "Chelsea Piers Fitness",
                                   "Pool + track · 75 min",
                                   reason="Closer, but a $50 day pass",
                                   distance_minutes=11, duration_minutes=75),
                        OptionSpec(rej, "ace_nyc", "Hotel fitness room",
                                   rejection_reason="No pool, and you asked for a swim",
                                   distance_minutes=0),
                    ],
                ),
                ItemSpec(
                    key="nyc_run", kind=ItemKind.activity,
                    status=ItemStatus.awaiting_user, window="nyc_afternoon",
                    starts=T(2, 15, 15), ends=T(2, 16),
                    options=[
                        OptionSpec(sel, "hudson_greenway", "Hudson River Greenway",
                                   "35-minute run · riverside",
                                   reason="Nine minutes from the hotel",
                                   distance_minutes=9, duration_minutes=35,
                                   matched_preferences=["Running"]),
                        OptionSpec(alt, "chelsea_piers", "Chelsea Piers Fitness",
                                   "Indoor track · 40 min",
                                   reason="If it rains",
                                   distance_minutes=11, duration_minutes=40),
                    ],
                ),
                ItemSpec(
                    key="nyc_dinner", kind=ItemKind.meal,
                    status=ItemStatus.awaiting_user, needs_reservation=True,
                    starts=T(2, 19), ends=T(2, 20, 30),
                    options=[
                        OptionSpec(sel, "dirt_candy", "Dirt Candy",
                                   "Vegetable tasting · $$",
                                   reason="Matches your vegetarian preference",
                                   distance_minutes=12,
                                   matched_preferences=["Vegetarian", "$$ or less"]),
                        OptionSpec(rej, "gramercy", "Gramercy Tavern",
                                   "New American · $$$$",
                                   rejection_reason="$$$$, well above the budget you set",
                                   distance_minutes=6),
                    ],
                ),
            ],
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="plan_ready", title="Your New York plan is ready",
            body="Three suggestions waiting on you.",
            cta={"label": "Review plan", "deep_link": "/trip?trip=newyork"},
            run="nyc_plan", status="sent",
            created=T(-7, 0, 3), sent=T(-7, 0, 3),
        ),
    ],
)


# --- Seattle: plan settled, two actions waiting on approval. ---------------

SEATTLE = TripSpec(
    key="seattle",
    city="Seattle", region="WA", timezone="America/Los_Angeles",
    lat=47.6062, lng=-122.3321,
    starts_in_days=33, nights=3,
    label="Design summit",
    state=TripState.confirmed,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.86,
    hotel="thompson_sea",
    evidence=[
        EvidenceSpec("conference_event", "Calendar", "Design Summit",
                     "Bell Harbor · 2 day blocks", "cal_evt_summit"),
        EvidenceSpec("hotel_email", "Email", "Thompson Seattle",
                     "110 Stewart St · 3 nights", "msg_thompson_conf"),
    ],
    calendar_events=[
        CalEventSpec("sea_summit_1", "Design Summit, day 1", T(1, 9), T(1, 17),
                     "Bell Harbor"),
        CalEventSpec("sea_summit_2", "Design Summit, day 2", T(2, 9), T(2, 16),
                     "Bell Harbor"),
    ],
    windows=[
        WindowSpec(
            key="sea_morning", local_day=1, starts=T(1, 6, 15), ends=T(1, 8),
            label="105 minutes before the summit",
            gap_explanation="Your first session is at 9:00.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Design Summit, day 1",
                          "Starts 9:00 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "Thompson Seattle",
                          "Pool is 14 minutes away", "Email"),
            ],
            status=WindowStatus.filled,
        ),
        WindowSpec(
            key="sea_evening", local_day=2, starts=T(2, 16, 30), ends=T(2, 18, 30),
            label="2 hours free",
            gap_explanation="The summit ends at 4:00 and nothing follows it.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Design Summit, day 2",
                          "Ends 4:00 PM", "Calendar"),
                BoundSpec("plan_item", "PLAN", "Dinner you kept",
                          "Starts 7:00 PM", "This plan"),
            ],
            status=WindowStatus.filled,
        ),
    ],
    events=[
        EventSpec("sea_activation", "scheduled_activation", T(-7, 0, 6),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
    ],
    runs=[
        RunSpec(
            key="sea_plan", kind="pretrip_plan", status="completed",
            trigger_event="sea_activation",
            started=T(-7, 0, 6), finished=T(-7, 0, 8),
            context_snapshot={"trip": {"city": "Seattle", "nights": 3},
                              "calendar_events_read": 5, "windows_found": 2},
            result={"items_proposed": 3, "windows_filled": 2},
        ),
    ],
    plans=[
        PlanSpec(
            version=1, status=PlanStatus.accepted, run="sea_plan",
            headline="A swim, a run and a table",
            provenance_summary=(
                "Prepared a week out · read 5 calendar events · found 2 open windows"
            ),
            items=[
                ItemSpec(
                    key="sea_swim", kind=ItemKind.activity,
                    status=ItemStatus.planned, window="sea_morning",
                    starts=T(1, 6, 30), ends=T(1, 7, 30),
                    options=[
                        OptionSpec(sel, "medgar_evers", "Medgar Evers Pool",
                                   "Lap swim · 60 min",
                                   reason="An $8 lap swim, inside your budget",
                                   distance_minutes=14, duration_minutes=60,
                                   matched_preferences=["Swim", "Mornings", "$$ or less"]),
                        OptionSpec(alt, "thompson_sea", "Hotel fitness room",
                                   "Treadmill · 40 min",
                                   reason="No travel time, but no pool",
                                   distance_minutes=0, duration_minutes=40),
                    ],
                ),
                ItemSpec(
                    key="sea_run", kind=ItemKind.activity,
                    status=ItemStatus.planned, window="sea_evening",
                    starts=T(2, 16, 45), ends=T(2, 17, 30),
                    options=[
                        OptionSpec(sel, "green_lake", "Green Lake Loop",
                                   "45-minute run · 2.8 mile loop",
                                   reason="A full loop with time to change",
                                   distance_minutes=16, duration_minutes=45,
                                   matched_preferences=["Running"]),
                    ],
                ),
                ItemSpec(
                    key="sea_dinner", kind=ItemKind.meal,
                    status=ItemStatus.planned, needs_reservation=True,
                    starts=T(2, 19), ends=T(2, 20, 30),
                    options=[
                        OptionSpec(sel, "cafe_flora", "Cafe Flora",
                                   "Vegetarian · $$",
                                   reason="Matches your vegetarian preference",
                                   distance_minutes=13,
                                   matched_preferences=["Vegetarian", "$$ or less"]),
                    ],
                ),
            ],
        ),
    ],
    actions=[
        ActionSpec(
            key="sea_cal_swim", type="create_calendar_event", status="proposed",
            subject_item="sea_swim", approval_required=True, proposed=T(-7, 0, 8),
            proposed_payload={"title": "Lap swim · Medgar Evers Pool",
                              "starts": "day 1, 6:30 AM", "ends": "day 1, 7:30 AM"},
        ),
        ActionSpec(
            key="sea_res", type="make_reservation", status="proposed",
            subject_item="sea_dinner", approval_required=True, proposed=T(-7, 0, 8),
            proposed_payload={"provider": "opentable", "place": "Cafe Flora",
                              "party_size": 1, "slot": "day 2, 7:00 PM"},
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="approval_needed", title="Two things need your approval",
            body="A calendar hold and a dinner reservation for Seattle.",
            cta={"label": "Review", "deep_link": "/trip?trip=seattle"},
            run="sea_plan", status="sent",
            created=T(-7, 0, 8), sent=T(-7, 0, 8),
        ),
    ],
)


# --- Detections: one card plus two rows, the density-adaptive layout. ------

AUSTIN = TripSpec(
    key="austin",
    city="Austin", region="TX", timezone="America/Chicago",
    lat=30.2672, lng=-97.7431,
    starts_in_days=45, nights=3,
    label="Client visit",
    state=TripState.detected,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.71,
    evidence=[
        EvidenceSpec("flight_event", "Calendar", "WN 288 · SFO to AUS",
                     "Round trip · confirmed", "cal_evt_wn288"),
        EvidenceSpec("calendar_block", "Calendar", "Client onsite",
                     "3 day block", "cal_evt_onsite"),
        EvidenceSpec("hotel_email", "Email", "South Congress Hotel",
                     "1603 S Congress Ave · 3 nights", "msg_soco_conf"),
    ],
    calendar_events=[
        CalEventSpec("aus_onsite", "Client onsite", T(1, 9), T(1, 17),
                     "South Congress"),
        CalEventSpec("aus_flight", "WN 288 · SFO to AUS", T(0, 7), T(0, 12, 15)),
    ],
    events=[
        EventSpec("aus_detect", "calendar_changed", T(-3, 11, 20),
                  {"added_events": 3, "cluster": "Austin, TX"}),
    ],
    runs=[
        RunSpec(
            key="aus_detect_run", kind="trip_detection", status="completed",
            trigger_event="aus_detect", started=T(-3, 11, 20), finished=T(-3, 11, 21),
            context_snapshot={"events_scanned": 42, "cluster_days": 3},
            result={"trip_detected": True, "confidence": 0.71},
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="trip_detected", title="Austin trip found",
            body="A flight, an onsite block and a hotel email.",
            cta={"label": "Confirm trip", "deep_link": "/trip?trip=austin"},
            run="aus_detect_run", status="sent",
            created=T(-3, 11, 21), sent=T(-3, 11, 21),
        ),
    ],
)

BOSTON = TripSpec(
    key="boston",
    city="Boston", region="MA", timezone="America/New_York",
    lat=42.3601, lng=-71.0589,
    starts_in_days=52, nights=3,
    label="Board meeting",
    state=TripState.detected,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.64,
    evidence=[
        EvidenceSpec("calendar_block", "Calendar", "Board meeting",
                     "2 day block", "cal_evt_board"),
        EvidenceSpec("flight_event", "Calendar", "B6 611 · SFO to BOS",
                     "Departs 6:00 AM · held", "cal_evt_b6611"),
    ],
    calendar_events=[
        CalEventSpec("bos_board", "Board meeting", T(1, 9), T(1, 16),
                     "Back Bay office"),
    ],
    events=[
        EventSpec("bos_detect", "calendar_changed", T(-2, 8, 45),
                  {"added_events": 2, "cluster": "Boston, MA"}),
    ],
    runs=[
        RunSpec(
            key="bos_detect_run", kind="trip_detection", status="completed",
            trigger_event="bos_detect", started=T(-2, 8, 45), finished=T(-2, 8, 46),
            context_snapshot={"events_scanned": 38, "cluster_days": 2},
            result={"trip_detected": True, "confidence": 0.64},
        ),
    ],
)

MIAMI = TripSpec(
    key="miami",
    city="Miami", region="FL", timezone="America/New_York",
    lat=25.7617, lng=-80.1918,
    starts_in_days=60, nights=3,
    label="Conference",
    state=TripState.detected,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.58,
    evidence=[
        EvidenceSpec("conference_event", "Calendar", "ScaleConf Miami",
                     "Miami Beach Convention Center", "cal_evt_scaleconf"),
        EvidenceSpec("hotel_email", "Email", "The Betsy",
                     "1440 Ocean Dr · 3 nights · unconfirmed", "msg_betsy_hold"),
    ],
    calendar_events=[
        CalEventSpec("mia_conf", "ScaleConf Miami", T(1, 9), T(1, 18),
                     "Convention Center", status="tentative"),
    ],
    events=[
        EventSpec("mia_detect", "calendar_changed", T(-1, 16, 5),
                  {"added_events": 2, "cluster": "Miami, FL"}),
    ],
    runs=[
        RunSpec(
            key="mia_detect_run", kind="trip_detection", status="completed",
            trigger_event="mia_detect", started=T(-1, 16, 5), finished=T(-1, 16, 6),
            context_snapshot={"events_scanned": 40, "cluster_days": 3},
            result={"trip_detected": True, "confidence": 0.58},
        ),
    ],
)


# --- Past: a finished trip and an older archived one. ----------------------

VANCOUVER = TripSpec(
    key="vancouver",
    city="Vancouver", region="BC", timezone="America/Vancouver",
    lat=49.2827, lng=-123.1207,
    starts_in_days=-30, nights=4,
    label="Partner summit",
    state=TripState.completed,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.89,
    hotel="opus_van",
    evidence=[
        EvidenceSpec("flight_event", "Calendar", "AC 554 · SFO to YVR",
                     "Round trip · confirmed", "cal_evt_ac554"),
        EvidenceSpec("hotel_email", "Email", "Opus Vancouver",
                     "322 Davie St · 4 nights", "msg_opus_conf"),
    ],
    calendar_events=[
        CalEventSpec("van_summit", "Partner summit", T(1, 9), T(1, 17), "Convention Centre"),
        CalEventSpec("van_dinner", "Partner dinner", T(2, 19), T(2, 22), "Yaletown"),
    ],
    windows=[
        WindowSpec(
            key="van_morning", local_day=1, starts=T(1, 6, 30), ends=T(1, 8, 15),
            label="105 minutes before the summit",
            gap_explanation="Your first session was at 9:00.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "Partner summit",
                          "Started 9:00 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "Opus Vancouver",
                          "Seawall is 8 minutes away", "Email"),
            ],
            status=WindowStatus.filled,
        ),
    ],
    events=[
        EventSpec("van_activation", "scheduled_activation", T(-7, 0, 2),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
    ],
    runs=[
        RunSpec(
            key="van_plan", kind="pretrip_plan", status="completed",
            trigger_event="van_activation",
            started=T(-7, 0, 2), finished=T(-7, 0, 4),
            context_snapshot={"trip": {"city": "Vancouver", "nights": 4},
                              "calendar_events_read": 6, "windows_found": 2},
            result={"items_proposed": 2, "windows_filled": 1},
        ),
    ],
    plans=[
        PlanSpec(
            version=1, status=PlanStatus.accepted, run="van_plan",
            headline="A seawall run and one dinner",
            provenance_summary=(
                "Prepared a week out · read 6 calendar events · found 2 open windows"
            ),
            items=[
                ItemSpec(
                    key="van_run", kind=ItemKind.activity,
                    status=ItemStatus.confirmed, window="van_morning",
                    starts=T(1, 6, 45), ends=T(1, 7, 45),
                    calendar_event_ref="cal_evt_twl_seawall",
                    options=[
                        OptionSpec(sel, "seawall", "Stanley Park Seawall",
                                   "50-minute run · waterfront",
                                   reason="Eight minutes from the hotel",
                                   distance_minutes=8, duration_minutes=50,
                                   matched_preferences=["Running", "Mornings"]),
                    ],
                ),
                ItemSpec(
                    key="van_dinner", kind=ItemKind.meal,
                    status=ItemStatus.confirmed, needs_reservation=True,
                    starts=T(3, 19), ends=T(3, 20, 30),
                    calendar_event_ref="cal_evt_twl_acorn",
                    options=[
                        OptionSpec(sel, "acorn", "The Acorn", "Vegetarian · $$",
                                   reason="Matches your vegetarian preference",
                                   distance_minutes=11,
                                   matched_preferences=["Vegetarian", "$$ or less"]),
                    ],
                ),
            ],
        ),
    ],
    actions=[
        ActionSpec(
            key="van_res", type="make_reservation", status="completed",
            subject_item="van_dinner", approval_required=True,
            proposed=T(-7, 0, 4), approved=T(-6, 8, 30), executed=T(-6, 8, 31),
            proposed_payload={"provider": "opentable", "place": "The Acorn",
                              "party_size": 1, "slot": "day 3, 7:00 PM"},
            execution_result={"confirmation_code": "#9K7C2", "status": "confirmed"},
            verification={"re_read_at": "day -6 8:32", "provider_status": "confirmed"},
        ),
    ],
    reservations=[
        ReservationSpec(
            provider="opentable", status="confirmed", item="van_dinner",
            place="acorn", slot=T(3, 19), party_size=1, confirmation_code="#9K7C2",
            external_url="https://www.opentable.com/r/the-acorn-vancouver",
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="plan_ready", title="Your Vancouver plan is ready",
            body="A seawall run and a table at The Acorn.",
            cta={"label": "Review plan", "deep_link": "/trip?trip=vancouver"},
            run="van_plan", status="opened",
            created=T(-7, 0, 4), sent=T(-7, 0, 4), opened=T(-6, 8, 25),
        ),
    ],
)

LONDON = TripSpec(
    key="london",
    city="London", region="England", timezone="Europe/London",
    lat=51.5072, lng=-0.1276,
    starts_in_days=-95, nights=6,
    label="EMEA roadshow",
    state=TripState.archived,
    # Carried over from a previous system rather than detected or hand-entered.
    origin=TripOrigin.import_,
    hotel="hoxton_ldn",
    calendar_events=[
        CalEventSpec("ldn_roadshow", "EMEA roadshow", T(1, 9), T(1, 18), "Holborn"),
        CalEventSpec("ldn_partner", "Partner briefing", T(4, 10), T(4, 15), "Shoreditch"),
    ],
    windows=[
        WindowSpec(
            key="ldn_morning", local_day=2, starts=T(2, 6, 30), ends=T(2, 8),
            label="90 minutes before the briefing",
            gap_explanation="Your first commitment was at 9:00.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "EMEA roadshow",
                          "Started 9:00 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "The Hoxton, Holborn",
                          "Pool is 5 minutes away", "Import"),
            ],
            status=WindowStatus.superseded,
        ),
        WindowSpec(
            key="ldn_morning_v2", local_day=2, starts=T(2, 7), ends=T(2, 8, 30),
            label="90 minutes before the briefing",
            gap_explanation="Your rescheduled first session was at 9:30.",
            bounds=[
                BoundSpec("calendar_event", "CAL", "EMEA roadshow",
                          "Moved to 9:30 AM", "Calendar"),
                BoundSpec("itinerary", "HTL", "The Hoxton, Holborn",
                          "Pool is 5 minutes away", "Import"),
            ],
            status=WindowStatus.filled,
        ),
    ],
    events=[
        EventSpec("ldn_activation", "scheduled_activation", T(-7, 0, 1),
                  {"reason": "T-7d activation", "trip_start": "day 0"}),
        EventSpec("ldn_change", "calendar_changed", T(1, 20, 15),
                  {"moved_event": "EMEA roadshow", "from": "9:00", "to": "9:30"}),
    ],
    runs=[
        RunSpec(
            key="ldn_plan", kind="pretrip_plan", status="completed",
            trigger_event="ldn_activation",
            started=T(-7, 0, 1), finished=T(-7, 0, 3),
            context_snapshot={"trip": {"city": "London", "nights": 6},
                              "calendar_events_read": 9, "windows_found": 3},
            result={"items_proposed": 2, "windows_filled": 1},
        ),
        RunSpec(
            key="ldn_replan", kind="replan_conflict", status="completed",
            trigger_event="ldn_change",
            started=T(1, 20, 15), finished=T(1, 20, 17),
            context_snapshot={"conflict": "EMEA roadshow moved 30 minutes later"},
            result={"plan_version": 2, "items_moved": 1},
        ),
    ],
    plans=[
        # v1 superseded by v2: history is kept, and the rollup query must ignore
        # the old version entirely.
        PlanSpec(
            version=1, status=PlanStatus.superseded, run="ldn_plan",
            headline="A morning swim before the roadshow",
            provenance_summary=(
                "Prepared a week out · read 9 calendar events · found 3 open windows"
            ),
            items=[
                ItemSpec(
                    key="ldn_swim_v1", kind=ItemKind.activity,
                    status=ItemStatus.changed, window="ldn_morning",
                    starts=T(2, 6, 45), ends=T(2, 7, 30),
                    options=[
                        OptionSpec(sel, "oasis_ldn", "Oasis Sports Centre",
                                   "Heated outdoor pool · 45 min",
                                   reason="Five minutes from the hotel",
                                   distance_minutes=5, duration_minutes=45,
                                   matched_preferences=["Swim", "Mornings"]),
                    ],
                ),
            ],
        ),
        PlanSpec(
            version=2, status=PlanStatus.accepted, run="ldn_replan",
            headline="Swim moved 30 minutes later",
            provenance_summary=(
                "Replanned after your roadshow moved · 1 item shifted"
            ),
            items=[
                ItemSpec(
                    key="ldn_swim_v2", kind=ItemKind.activity,
                    status=ItemStatus.confirmed, window="ldn_morning_v2",
                    starts=T(2, 7, 15), ends=T(2, 8),
                    calendar_event_ref="cal_evt_twl_oasis",
                    options=[
                        OptionSpec(sel, "oasis_ldn", "Oasis Sports Centre",
                                   "Heated outdoor pool · 45 min",
                                   reason="Shifted to clear your 9:30 start",
                                   distance_minutes=5, duration_minutes=45,
                                   matched_preferences=["Swim", "Mornings"]),
                    ],
                ),
                # Stays on the plan: OpenTable declined, the user did not remove
                # it. `removed` is a tombstone and hides the row that carries the
                # failed booking.
                ItemSpec(
                    key="ldn_dinner_v2", kind=ItemKind.meal,
                    status=ItemStatus.planned, needs_reservation=True,
                    starts=T(4, 19), ends=T(4, 20, 30),
                    options=[
                        OptionSpec(sel, "mildreds", "Mildreds Soho",
                                   "Vegetarian · $$",
                                   reason="Matches your vegetarian preference",
                                   distance_minutes=14,
                                   matched_preferences=["Vegetarian"]),
                    ],
                ),
            ],
        ),
    ],
    actions=[
        ActionSpec(
            key="ldn_cal_update", type="update_calendar_event", status="completed",
            subject_item="ldn_swim_v2", approval_required=False,
            proposed=T(1, 20, 17), approved=T(1, 20, 17), executed=T(1, 20, 18),
            proposed_payload={"event_id": "cal_evt_twl_oasis",
                              "starts": "day 2, 7:15 AM", "ends": "day 2, 8:00 AM"},
            execution_result={"event_id": "cal_evt_twl_oasis", "status": "updated"},
            verification={"re_read_at": "day 1 20:19", "starts": "day 2, 7:15 AM"},
        ),
        # A reservation the provider declined: the failure path, end to end.
        ActionSpec(
            key="ldn_res_failed", type="make_reservation", status="failed",
            subject_item="ldn_dinner_v2", approval_required=True,
            proposed=T(1, 20, 17), approved=T(2, 9, 5), executed=T(2, 9, 6),
            proposed_payload={"provider": "opentable", "place": "Mildreds Soho",
                              "party_size": 1, "slot": "day 4, 7:00 PM"},
            execution_result={"status": "declined",
                              "provider_message": "No tables at that time"},
        ),
    ],
    reservations=[
        ReservationSpec(
            provider="opentable", status="failed", item="ldn_dinner_v2",
            place="mildreds", slot=T(4, 19), party_size=1,
            failure_reason="Mildreds declined the 7:00 hold",
            external_url="https://www.opentable.co.uk/r/mildreds-soho",
        ),
    ],
    notifications=[
        NotificationSpec(
            kind="schedule_conflict", title="Your London schedule changed",
            body="The roadshow moved to 9:30; your swim moved with it.",
            cta={"label": "See the change", "deep_link": "/trip?trip=london"},
            run="ldn_replan", status="opened",
            created=T(1, 20, 17), sent=T(1, 20, 17), opened=T(2, 7, 2),
        ),
        NotificationSpec(
            kind="reservation_failed", title="Mildreds could not take the booking",
            body="No tables at 7:00. Nothing was charged.",
            cta={"label": "Pick another", "deep_link": "/trip?trip=london"},
            status="dismissed", created=T(2, 9, 6), sent=T(2, 9, 6),
        ),
    ],
)


# --- Dismissed: proves a rejected detection disappears everywhere. ---------

NASHVILLE = TripSpec(
    key="nashville",
    city="Nashville", region="TN", timezone="America/Chicago",
    lat=36.1627, lng=-86.7816,
    starts_in_days=10, nights=1,
    label="Offsite",
    state=TripState.dismissed,
    origin=TripOrigin.calendar_detection,
    detection_confidence=0.42,
    evidence=[
        EvidenceSpec("calendar_block", "Calendar", "Nashville sync",
                     "Single 2-hour block", "cal_evt_nash"),
    ],
    calendar_events=[
        CalEventSpec("nash_sync", "Nashville sync", T(0, 14), T(0, 16), None),
    ],
    events=[
        EventSpec("nash_detect", "calendar_changed", T(-4, 10),
                  {"added_events": 1, "cluster": "Nashville, TN"}),
        EventSpec("nash_dismiss", "ui_action", T(-4, 18, 30),
                  {"action": "dismiss_trip", "reason": "video call, not travel"}),
    ],
    runs=[
        RunSpec(
            key="nash_detect_run", kind="trip_detection", status="completed",
            trigger_event="nash_detect", started=T(-4, 10), finished=T(-4, 10, 1),
            context_snapshot={"events_scanned": 36, "cluster_days": 1},
            result={"trip_detected": True, "confidence": 0.42},
        ),
    ],
)


TRIPS = [
    CHICAGO, PORTLAND, DENVER, NEW_YORK, SEATTLE,
    AUSTIN, BOSTON, MIAMI,
    VANCOUVER, LONDON, NASHVILLE,
]
