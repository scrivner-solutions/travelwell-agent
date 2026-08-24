---
name: research-intelligence
description: Discovers candidate wellness facilities, collects metadata, identifies access information, and preserves uncertainty.
version: 1.0.0
inputs:
  - location
  - budget_cap
  - memberships
  - preferred_amenities
outputs:
  - trip_profile
  - resolved_location
  - candidate_facilities
  - data_source
  - data_warnings
tags:
  - research
  - discovery
  - metadata
  - scraper
  - places
---

# Research & Intelligence Agent Skill

The Research & Intelligence Agent discovers potential workout locations and compiles comprehensive reports on facility access, pricing, schedules, and amenities.

## Responsibilities
1. **Facility Discovery**: Query Places services to find gyms, YMCA centers, and recreation facilities.
2. **Access & Pricing Analysis**: Locate guest pass options, local registration requirements, and membership reciprocity opportunities.
3. **Operational Profiling**: Extract facility hours, pool schedules, amenity checklists, and customer feedback.
4. **Preserving Uncertainty**: Record unknown variables as "not identified" rather than making logical assumptions.

## Rules
- **No Hallucinated Pricing**: If pricing cannot be verified via tools, report it as "Pricing information not identified." Do not invent trial passes or membership rates.
- **Budget Cap Enforcement**: Stop tool execution immediately and ask for clarification if a budget parameters is ambiguous (e.g. contains words like "under" but lacks a value).
- **Evidence Hierarchy**: Google Places is discovery data, not final truth for facility operations. Official facility pages should be treated as stronger evidence when available.

## Uncertainty Handling
- If free parking is not returned in the tools output, report: `"Free parking was not identified in the available facility data."` Do not output "No parking" or "Free parking likely available."
- Maintain strict separation between what is returned by the scraper tools and general world knowledge.

## Examples

### Correct Behavior
* **Input Context**: Scraper returns YMCA details but has no field for parking.
* **Output**: `"Free parking was not identified in the available facility data."` (Uncertainty preserved).

### Incorrect Behavior
* **Input Context**: Scraper returns YMCA details with no field for parking.
* **Output**: `"YMCA offers free parking for members."` (Hallucinated assumption).
