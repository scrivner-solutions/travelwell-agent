# Ranking and Itinerary Rules

## Ranking Philosophy
- **Mandatory Constraints First**: A facility must satisfy all mandatory constraints (e.g. budget cap, YMCA reciprocity, required amenities like showers) before its scoring weights are computed.
- **Scoring Scale**: Score facilities on a weighted scale from 0 to 100 based on scoring weights configuration.
- **Exactly 3 Options**: Always output exactly 3 options if 3 candidate facilities exist.
- **Realistic Routing Buffers**: Use actual tool output walk/drive durations. Never invent arbitrary times.

## Uncertainty Handling
- If routing fails, flag the travel times clearly instead of estimating them manually.
- Never add fictional segments to the itinerary (e.g. hotel check-out) unless requested or specified in the prompt window.
