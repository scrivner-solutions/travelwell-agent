---
name: ranking-itinerary
description: Ranks candidate wellness facilities, estimates visit feasibility, compares travel times, and creates timeline summaries.
version: 1.0.0
inputs:
  - facility_research_findings
  - user_preferences
  - travel_window
outputs:
  - ranked_recommendations
  - selected_facility
  - visit_fit_summary
  - ranking_rationale
tags:
  - ranking
  - itinerary
  - travel_time
  - routing
---

# Ranking & Itinerary Agent Skill

The Ranking & Itinerary Agent processes candidate facility reports to rank options and organize them into realistic travel itineraries.

## Responsibilities
1. **Distance & Routing Calculation**: Query routing services to evaluate walk/drive durations from coordinates.
2. **Weighted Preference Ranking**: Rank facilities by prioritizing mandatory criteria first (reciprocity benefits, strict budgets, required amenities) followed by user conveniences.
3. **Visit Feasibility Planning**: Construct structured workout timelines using travel windows and estimated visit durations.

## Inputs
- `facility_research_findings`
- `user_preferences`
- `travel_window`

## Outputs
- `ranked_recommendations`
- `selected_facility`
- `visit_fit_summary`
- `ranking_rationale`

## Workflow
1. Parse the discovered facilities and active traveler preferences/constraints.
2. Filter/flag facilities by compliance with mandatory parameters.
3. Compute weighted scoring using configured weights.
4. Construct itineraries with exact route segments.
5. Format the final output list.

## References & Resources

### Policies and Rules
- Core ranking philosophy, pricing logic, and routing rules: [ranking_rules.md](file:///Users/olgascrivner/Documents/WTM%20Ambassador/Kaggle/travelwell-ai/skills/ranking-itinerary/resources/ranking_rules.md)
- Scoring weights configuration schema: [scoring_weights.json](file:///Users/olgascrivner/Documents/WTM%20Ambassador/Kaggle/travelwell-ai/skills/ranking-itinerary/resources/scoring_weights.json)

### Examples
- YMCA reciprocity wins: [free_ymca_member_wins.md](file:///Users/olgascrivner/Documents/WTM%20Ambassador/Kaggle/travelwell-ai/skills/ranking-itinerary/examples/free_ymca_member_wins.md)
- Handling of budget exclusions: [free_only_rejects_paid_gym.md](file:///Users/olgascrivner/Documents/WTM%20Ambassador/Kaggle/travelwell-ai/skills/ranking-itinerary/examples/free_only_rejects_paid_gym.md)
- Handling of unverified pricing fields: [unknown_price_lower_confidence.md](file:///Users/olgascrivner/Documents/WTM%20Ambassador/Kaggle/travelwell-ai/skills/ranking-itinerary/examples/unknown_price_lower_confidence.md)
- Handling of routing matrix service errors: [routing_service_failure.md](file:///Users/olgascrivner/Documents/WTM%20Ambassador/Kaggle/travelwell-ai/skills/ranking-itinerary/examples/routing_service_failure.md)
