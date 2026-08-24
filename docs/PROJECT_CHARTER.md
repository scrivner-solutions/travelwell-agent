# TravelWell AI Project Charter
TravelWell AI demonstrates how specialized AI agents can collaborate to solve a real-world travel wellness problem through structured discovery, research, reasoning, ranking, and visualization.

TravelWell AI is an AI wellness concierge for travelers. It helps users maintain their fitness and wellness routines while traveling by finding the best nearby gyms, pools, recreation centers, walking routes, and wellness options based on location, time window, memberships, budget, preferences, and real-world facility details.

TravelWell AI emphasizes quality over quantity, recommending the three best options rather than overwhelming users with every nearby facility.

## Core Problem

Travelers often lose their wellness routines because finding a good fitness option requires checking maps, facility websites, hours, guest pass rules, pool schedules, reviews, parking, towel availability, booking requirements, and travel time manually.

TravelWell AI reduces this friction by using a multi-agent workflow to discover, research, rank, and schedule the best wellness option for a trip.

## MVP Scenario

A user says:

“I’ll be in downtown Chicago tomorrow from 6–9 PM. I have a YMCA membership, but I’m willing to pay up to $20 for a day pass. I prefer an indoor pool or treadmill, need showers, and would like to avoid places that are overcrowded or poorly reviewed.”

The app should return:

* Top recommended fitness/wellness locations
* Map-style visual summary
* Emoji-based amenity indicators
* Short explanation of why each option was chosen
* Suggested schedule/itinerary
* Agent workflow trace showing how the recommendation was produced

## Track Fit

Primary hackathon track: Concierge Agents.

TravelWell AI acts as a personalized travel wellness concierge rather than a generic travel planner.

## Core Agents

### 1. Trip Context Agent

Purpose:
Extracts and structures the user's travel request into a normalized trip profile.

Skills:
- Natural language understanding
- Preference extraction
- Date/time parsing
- Location normalization
- Budget interpretation
- Constraint identification
- User profile integration (future)

Outputs:
- Structured Trip Profile

---

### 2. Fitness Discovery Agent

Purpose:
Discovers candidate wellness facilities near the user's destination.

Skills:
- Geographic search
- Google Places search
- Nearby facility discovery
- Category filtering
- Radius optimization
- Candidate deduplication

Outputs:
- Candidate Facility List

---

### 3. Access & Membership Agent

Purpose:
Determines whether the traveler can realistically access each facility.

Skills:
- Membership compatibility
- Day-pass discovery
- Guest pass identification
- Free trial detection
- Pricing extraction
- Budget validation

Outputs:
- Accessible Facility List

---

### 4. Facility Intelligence Agent

Purpose:
Builds an intelligence profile for each candidate facility.

Skills:
- Website analysis
- Amenity extraction
- Hours verification
- Review summarization
- Policy extraction
- Parking analysis
- Pool availability analysis
- Booking requirement detection
- Crowd sentiment analysis
- Safety signal identification

Outputs:
- Facility Intelligence Report

---

### 5. Ranking Agent

Purpose:
Evaluates all facilities and recommends the best options.

Skills:
- Multi-criteria decision analysis
- Preference matching
- Weighted scoring
- Distance optimization
- Time compatibility analysis
- Confidence scoring
- Recommendation explanation

Outputs:
- Ranked Recommendations

---

### 6. Itinerary Agent

Purpose:
Produces a realistic wellness schedule around the user's travel plans.

Skills:
- Route planning
- Travel time estimation
- Schedule optimization
- Buffer time calculation
- Calendar generation

Outputs:
- Personalized Wellness Itinerary

---

### 7. Visualization Agent

Purpose:
Transforms recommendations into an intuitive visual experience.

Skills:
- Interactive map generation
- Recommendation cards
- Emoji amenity visualization
- Timeline visualization
- Route visualization
- Agent workflow visualization

Outputs:
- Interactive TravelWell Dashboard


## Project Architecture

Use Google ADK with a TypeScript/Node.js application structure.

Proposed folders:

travelwell-ai/
├── config/
├── docs/
├── frontend/
├── src/
│   ├── agents/
│   ├── skills/
│   ├── tools/
│   ├── workflows/
│   ├── services/
│   ├── types/
│   ├── utils/
│   └── index.ts
├── tests/
├── .env.example
├── .gitignore
├── package.json
└── tsconfig.json

## Agent Registry and Agent Cards

Include an agent registry that exports all available agents for orchestration.

Include agent cards that describe each agent’s purpose, inputs, outputs, tools, and role in the workflow.

The agent cards should be usable in the frontend to show an agent graph or execution trace.

## Tools and Services

Design tools/services so agents do not directly call external APIs.

Possible services:

* Places search service
* Facility details service
* Review summarization service
* Map routing service
* Weather service, optional
* Mock data service for reliable demo fallback

The MVP should support mock or seeded data so the demo works even if APIs are limited.

Agents should encapsulate business logic.
Reusable capabilities should be implemented as Skills.
External integrations should be exposed through Tools and Services.

## UI Requirements

The frontend should feel like a lightweight “Waze for travel wellness.”

Core UI elements:

* User trip request form
* Map or map-like visual panel
* Top recommendation cards
* Emoji amenity badges
* Suggested schedule
* Agent graph or agent progress timeline
* Explanation of why the top option was selected

Suggested amenity icons:

🏊 Indoor pool
🏃 Treadmill
🚿 Showers
🧺 Towels
🔒 Lockers
🅿️ Parking
💵 Day pass
📅 Booking required
🚶 Walkable
⭐ Highly rated
🔥 Crowding or comfort warning

## Technical Priorities

Prioritize:

* Clean architecture
* Modular agents
* Reusable tools/services
* Strong TypeScript types
* Demo reliability
* Clear README
* Visual polish
* Explainable recommendation flow

Avoid:

* Overbuilding authentication
* Complex persistent memory
* Overly broad travel planning
* Unsupported claims about real-time availability
* Depending entirely on live APIs for the demo

## Definition of Done for MVP

The project is complete when a user can enter a travel wellness request and receive:

1. A structured interpretation of their request
2. Three ranked wellness options
3. Emoji-based amenity summaries
4. A recommended schedule
5. A clear explanation of the top recommendation
6. A visible multi-agent workflow trace
7. A professional README documenting the project architecture, agent workflow, setup instructions, and demo scenario.
8. The primary demo scenario should work flawlessly before additional features are implemented.
9. A responsive interactive map displaying the recommended wellness locations and key facility information.

## Success Criteria

The MVP should demonstrate:

- Clear collaboration between multiple specialized AI agents
- Explainable recommendation generation
- A polished, intuitive user experience
- Clean, modular architecture suitable for future expansion
- Reliable demo execution using mock or live data


## Non-Goals

The MVP will not:

- Book or purchase memberships
- Process payments
- Reserve facilities automatically
- Replace Google Maps navigation
- Guarantee real-time facility availability
- Maintain long-term user profiles
- Support every type of wellness activity
## Design Principles

- Simplicity over feature richness
- Explainable recommendations
- Clean modular architecture
- Mobile-first interface
- Graceful fallback when APIs are unavailable
- Mock data should always support a complete demo
## Technology Stack
Google ADK
TypeScript
Node.js
React
Google Maps
Gemini
Cloud Run
## Future versions may include:

- Hotel gyms
- Running routes
- Healthy restaurants
- Hiking trails
- Pickleball
- Yoga
- Wellness itinerary across multiple days
- Persistent traveler preferences

## Demo Requirements

The application must remain fully demonstrable even if external APIs are unavailable.

All core workflows should support deterministic mock data.
