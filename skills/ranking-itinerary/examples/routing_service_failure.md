# Example: Routing Service Failure
- **Input**: Gym coordinates resolved, but routing matrices API returns a 500 error or empty routes.
- **Expected Action**: Rank the facility but flag the distance and travel time as "Unknown (Routing API unavailable)". Do not hallucinate walking times like "5 min walk based on distance".
