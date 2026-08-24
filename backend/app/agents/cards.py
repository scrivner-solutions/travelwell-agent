from typing import Dict, Any, List

STAGE_CARDS: List[Dict[str, Any]] = [
    {
        "id": "trip_context",
        "name": "Trip Context Agent",
        "logical_stage": "Trip Context",
        "purpose": "Extracts and normalizes traveler parameters and constraints.",
        "inputs": ["Raw travel prompt"],
        "outputs": ["Structured Trip Profile"],
        "role_in_workflow": "Parses locations, times, budget caps, memberships, and preferences from natural language.",
        "tools": []
    },
    {
        "id": "fitness_discovery",
        "name": "Fitness Discovery Agent",
        "logical_stage": "Fitness Discovery",
        "purpose": "Locates candidates and facilities near the destination.",
        "inputs": ["Coordinates", "Search Radius", "Category Filters"],
        "outputs": ["Candidate Facility List"],
        "role_in_workflow": "Queries local map databases for nearby gyms, pools, and recreation facilities.",
        "tools": ["places_service"]
    },
    {
        "id": "access_membership",
        "name": "Access & Membership Agent",
        "logical_stage": "Access & Membership",
        "purpose": "Determines pricing, eligibility, and day-pass compatibility.",
        "inputs": ["Candidate Facility List", "Traveler Memberships", "Budget Cap"],
        "outputs": ["Accessible Facility List"],
        "role_in_workflow": "Validates pricing rules and detects free guest trials or reciprocity rights.",
        "tools": ["scraper_service"]
    },
    {
        "id": "facility_intelligence",
        "name": "Facility Intelligence Agent",
        "logical_stage": "Facility Intelligence",
        "purpose": "Compiles schedule, amenity, and crowding profiles.",
        "inputs": ["Accessible Facility List"],
        "outputs": ["Detailed Facility Reports"],
        "role_in_workflow": "Retrieves open hours, pool slot tables, and crowds/reviews sentiment.",
        "tools": ["scraper_service"]
    },
    {
        "id": "ranking",
        "name": "Ranking Agent",
        "logical_stage": "Ranking",
        "purpose": "Applies multi-criteria scoring to identify the top 3 recommendations.",
        "inputs": ["Detailed Facility Reports", "User Preferences"],
        "outputs": ["Ranked Recommendations List"],
        "role_in_workflow": "Applies scoring weights matching user preferences (prioritizing mandatory criteria first).",
        "tools": []
    },
    {
        "id": "itinerary",
        "name": "Itinerary Agent",
        "logical_stage": "Itinerary",
        "purpose": "Generates a realistic schedule with transit buffers.",
        "inputs": ["Ranked Recommendations List", "Trip Time Window"],
        "outputs": ["Personalized Workout Timeline"],
        "role_in_workflow": "Computes walking or driving times and wraps workouts into safe time buffers.",
        "tools": ["routing_service"]
    },
    {
        "id": "policy_validation",
        "name": "Policy & Validation Layer",
        "logical_stage": "Policy & Validation Layer",
        "purpose": "Deterministically evaluates recommendations against explicit user rules.",
        "inputs": ["Personalized Workout Timeline", "Ranked Recommendations List"],
        "outputs": ["Verified Recommendation Results"],
        "role_in_workflow": "Enforces policies such as budget constraints, hours matching, required amenities, and safety rules.",
        "tools": []
    }
]
