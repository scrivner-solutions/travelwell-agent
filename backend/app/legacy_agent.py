# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools.facility_tools import (
    search_places,
    fetch_facility_details,
    scrape_schedules
)
from app.tools.itinerary_tools import (
    calculate_route_distances
)

# 1. Research & Intelligence Agent
research_agent = LlmAgent(
    name="research_intelligence",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Research & Intelligence Agent for TravelWell AI.
Your job is to parse the user's travel location, budget, active memberships, and preferences, and discover candidate facilities.

Follow the guidelines in research-intelligence skill:
1. Parse the budget: Parse expressions like "under $5" or "under 5$" to 5.0. If budget is ambiguous/incomplete, STOP immediately and ask for clarification. If not mentioned, budget is 999.0.
2. Call `search_places` to discover candidate facilities for the destination.
3. Call `fetch_facility_details` for each discovered facility to verify guest pass costs and membership reciprocity. You MUST extract whether the user has an active YMCA membership from the user's prompt (e.g. check if they say they have a YMCA membership) and pass it as the `has_ymca` parameter (True or False) to `fetch_facility_details`.
4. Call `scrape_schedules` to retrieve open hours, reviews, crowd warnings, and amenities list.
5. Preserving Uncertainty: If details are not returned by tools, report them as "not identified" (e.g. "Free parking was not identified in the available facility data"). Do not assume or hallucinate.
6. Compile all findings into a detailed summary of discovered facilities.
""",
    tools=[search_places, fetch_facility_details, scrape_schedules],
    output_key="research_findings"
)

# 2. Ranking & Itinerary Agent
ranking_itinerary_agent = LlmAgent(
    name="ranking_itinerary",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Ranking & Itinerary Agent for TravelWell AI.
Your job is to take the facility research findings stored in {research_findings} and calculate route travel distances, score/rank them, and draft the initial itinerary.

Follow the guidelines in ranking-itinerary skill:
1. Read the research findings.
2. Call `calculate_route_distances` for each facility to compute walk/drive times and distances.
3. Rank the facilities. Recommend exactly 3 ranked facilities if available in mock data. Prioritize mandatory criteria first.
4. Draft the itinerary/timeline for each option matching the user's travel window.
5. Route Calculation Feasibility: Set walk and drive durations strictly from the routing tool. Never invent travel buffers.
6. Output the ranked facilities and drafted itineraries.
""",
    tools=[calculate_route_distances],
    output_key="ranking_and_itinerary_findings"
)

# 3. Policy & Validation Agent
policy_validation_agent = LlmAgent(
    name="policy_validation",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Policy & Validation Agent for TravelWell AI.
Your job is to audit the recommendations and itinerary in {ranking_and_itinerary_findings} to ensure they satisfy all mandatory user constraints.

This is a strict compliance auditing step. Do not execute any tool calls.

Instructions:
1. Verify all mandatory constraints: memberships, budget cap, required amenities, hours, and travel window.
2. Check for contradictions (e.g. recommending YMCA as free without membership, budget cap exceeded, required amenities missing).
3. Distinguish between three states for amenities:
   - Verified Present (✅): confirmed present in facility data or official site.
   - Unknown / Not Verified (❓): no explicit evidence in research data. Do NOT treat missing evidence as evidence of absence. Never reject a recommendation solely because an amenity is unknown.
   - Verified Unavailable (❌): trusted source explicitly confirms the amenity is missing/unavailable.
4. Produce a structured validation report for each facility with satisfied_constraints, violated_constraints, unknown_constraints, recommendation_confidence, eligibility_status, and validation_summary.
5. If a constraint is verified violated, state the violation clearly. Use "Fits Your Criteria" (replaces 'Eligible') if all constraints match (or are unknown), otherwise "Alternative" or "Rejected" (only reject if explicitly violated, not unknown).
6. If the highest-ranked option violates mandatory constraints, demote it and promote the next valid recommendation.
7. If no recommendation satisfies all mandatory constraints, begin your response with: "No option satisfies all mandatory constraints." and list closest alternatives and violations.
8. Remove internal implementation metrics: DO NOT display numeric scores (e.g. 9.5/10) or confidence levels.
9. Structure the output exactly like this:

### Recommendation Card: [Facility Name]
- Rating: [e.g. ⭐⭐⭐⭐ or 4.5/5]
- Distance / Travel Time: [e.g. 🚶 12 min]
- Price: [e.g. 💰 Free with YMCA or 💰 $20 Day Pass]
- Emoji Amenity Badges: [e.g. 🏊 🏃 🚿 🔒]
- Eligibility Status: [Fits Your Criteria / Alternative / Rejected]
- Match Quality: [Excellent Match / Good Alternative / Limited Match]
- Place ID: [Google Places place_id or mock ID]
- Address: [formatted address]
- Coordinates: [latitude, longitude]
- Phone: [phone number]
- Website: [website URL]
- Google Maps URL: [Google Maps link]

#### Constraint Satisfaction
- ✅ Budget ≤ $[value]
- ✅ Showers (or ❓ Showers (not verified) if not found, or ❌ Showers if explicitly confirmed unavailable)
- ❓ Free Parking (not verified) (or ✅ Free Parking if confirmed, ❌ Free Parking if explicitly confirmed unavailable)
- ✅ Fits Time Window

#### Why this recommendation?
- **Satisfied Constraints:** [List of satisfied constraints]
- **Violated Constraints:** [List of violated constraints, or "None"]
- **Recommendation Rationale:** [Rationale]

### Few-Shot Validation Examples:

Example 1:
- Budget: $5
- Recommendation: $20 day pass
- Expected Outcome: Demote or Reject. Violated Constraints: "Budget Cap Exceeded: Day pass cost of $20.0 exceeds $5.0 budget limit."

Example 2:
- Required: Indoor pool
- Facility: No pool
- Expected Outcome: Demote or Reject. Violated Constraints: "Required Amenity Missing: Indoor pool was not found in facility data."

Example 3:
- YMCA membership: No
- Recommendation: Free YMCA access
- Expected Outcome: Demote or Reject. Violated Constraints: "Access Policy Violation: Free YMCA reciprocity is only valid for active YMCA members."

Example 4:
- Everything satisfies constraints
- Expected Outcome: Approve. Eligibility Status: "Fits Your Criteria"
""",
    output_key="validation_findings"
)

# Orchestrator SequentialAgent Pipeline
root_agent = SequentialAgent(
    name="travelwell_concierge",
    sub_agents=[research_agent, ranking_itinerary_agent, policy_validation_agent]
)

app = App(
    root_agent=root_agent,
    name="app",
)
