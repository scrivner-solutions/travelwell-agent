from pydantic import BaseModel, Field
from typing import List, Optional

class UserRequest(BaseModel):
    prompt: str = Field(description="The user's raw input prompt containing trip details, budget, memberships, preferences, etc.")
    use_mock_data: Optional[bool] = Field(default=True, description="Whether to bypass live APIs and run strictly using mock datasets.")

class TripProfile(BaseModel):
    location: str
    start_time: str
    end_time: str
    budget: float
    memberships: List[str]
    preferences: List[str]
    required_amenities: List[str]
    access_preferences: Optional[List[str]] = Field(default_factory=list)
    free_text_preferences: Optional[str] = None

class Pricing(BaseModel):
    access_type: str
    cost: float
    pass_detail: str

class Hours(BaseModel):
    open: str
    close: str
    warning: Optional[str] = None

class Distance(BaseModel):
    value_miles: float
    walking_time_minutes: int
    transit_time_minutes: int
    description: str

class MapMarker(BaseModel):
    lat: float
    lng: float
    label: str
    title: str

class Facility(BaseModel):
    id: str
    name: str
    address: str
    rating: float
    amenities: List[str]
    emoji_badges: List[str]
    pricing: Pricing
    hours: Hours
    distance: Distance
    map_marker: MapMarker
    reviews_summary: str
    crowd_warning: Optional[str] = None

class RecommendedFacility(BaseModel):
    facility: Facility
    rank: int
    score: float
    confidence: float
    recommendation_reason: str

class ItineraryItem(BaseModel):
    time_window: str
    activity: str
    duration_minutes: int
    type: str
    details: str

class Metadata(BaseModel):
    data_mode: str
    sources_used: List[str]
    generated_at: str

class TraceEvent(BaseModel):
    stage: str
    status: str
    progress: int
    message: str

class FacilityRecommendation(BaseModel):
    id: str
    place_id: str
    name: str
    display_name: str
    address: str
    formatted_address: str
    coordinates: dict
    rating: float
    walk_minutes: Optional[int] = None
    drive_minutes: Optional[int] = None
    distance_miles: Optional[float] = None
    effective_price: Optional[float] = None
    day_pass_price: Optional[float] = None
    pricing_status: str
    access_status: str
    access_type: str
    is_open_now: bool
    opening_hours_summary: str
    amenities: List[str] = Field(default_factory=list)
    amenity_states: Optional[dict] = Field(default_factory=dict)
    amenity_sources: Optional[dict] = Field(default_factory=dict)
    google_maps_url: str
    official_website_url: str
    validation_status: str
    eligibility_status: str
    confidence: float
    explanation: str
    data_warnings: List[str] = Field(default_factory=list)

class ConciergeResponse(BaseModel):
    trip_profile: TripProfile
    recommendations: List[RecommendedFacility]
    itinerary: List[ItineraryItem]
    metadata: Metadata
    trace: List[TraceEvent]
