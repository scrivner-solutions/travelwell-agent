# TravelWell AI Architecture Specification

TravelWell AI utilizes a hybrid architecture featuring a Python backend powered by the Google Agent Development Kit (ADK) and FastAPI, combined with a TypeScript/React frontend.

---

## Component Diagram

The following diagram illustrates the relationship between the client application, API routing layer, ADK multi-agent orchestrator, tools, and external services:

```mermaid
graph TB
    subgraph Client [React Frontend Application]
        UI[Interactive UI Component]
        Map[Google Maps Component]
        APIC[API Client client.ts]
        UI --> APIC
        Map --> APIC
    end

    subgraph API [API Serving Layer - FastAPI]
        APIC --> CORS[CORS Middleware]
        CORS --> RecRoute[POST /api/recommend]
        CORS --> ConfigRoute[GET /api/config]
        CORS --> GeocodeRoute[GET /resolve_location]
    end

    subgraph ADK [Orchestration Layer - Google ADK]
        RecRoute --> SeqAgent[SequentialAgent Runner]
        SeqAgent --> ResearchAgent[Research & Intelligence Agent]
        SeqAgent --> RankingAgent[Ranking & Itinerary Agent]
        SeqAgent --> PolicyAgent[Policy & Validation Agent]
    end

    subgraph Tools [Agent Tool Ecosystem]
        ResearchAgent --> GMapTool[google_maps_geocoding]
        ResearchAgent --> GPlacesTool[google_places_search]
        RankingAgent --> GRoutesTool[google_maps_routes]
    end

    subgraph Cloud [External API & Cloud Services]
        GMapTool --> GGeocode[Google Geocoding API]
        GPlacesTool --> GPlaces[Google Places Text Search / Details]
        GRoutesTool --> GRoutes[Google Routes API]
        SeqAgent --> Vertex[Google Vertex AI / Gemini]
    end

    subgraph DB [State & Sessions]
        SeqAgent --> Sessions[InMemory / VertexAi Session Service]
    end

    style Client fill:#d4ebf2,stroke:#333,stroke-width:2px
    style API fill:#e8f0fe,stroke:#333,stroke-width:2px
    style ADK fill:#fce8e6,stroke:#333,stroke-width:2px
    style Tools fill:#fef7e0,stroke:#333,stroke-width:2px
    style Cloud fill:#e6f4ea,stroke:#333,stroke-width:2px
```

---

## Execution Sequence Diagram

The diagram below details the sequence of interactions that occur from the moment a traveler submits a search query until the final explainable recommendation cards and map markers are rendered:

```mermaid
sequenceDiagram
    autonumber
    actor User as Traveler (Browser)
    participant FE as React Frontend
    participant BE as FastAPI Backend
    participant AG as Sequential Agent (ADK)
    participant RT as Research Agent
    participant RK as Ranking Agent
    participant PV as Policy Agent
    participant GO as Google Maps APIs
    participant VX as Vertex AI (Gemini)

    User->>FE: Enter Location, Budget, & YMCA Membership
    FE->>BE: GET /resolve_location?address=Willis+Tower
    BE->>GO: Geocode landmark address / Places fallback
    GO-->>BE: Resolved Display Name, Coordinates & Full Address
    BE-->>FE: Return geocoded coordinates & display details
    FE->>BE: POST /api/recommend (Search Parameters & Coordinates)
    BE->>AG: Initialize session & Run Sequential Pipeline

    Note over AG,RT: Stage 1-4: Research & Intelligence
    AG->>RT: Invoke Research Agent with Prompt
    RT->>VX: Query Vertex AI for reasoning
    RT->>GO: search_places & fetch_facility_details
    GO-->>RT: Gym lists, open hours, prices, amenities
    RT-->>BE: Yield research_intelligence state stream
    BE-->>FE: Stream Stage 2-4 progress updates (SSE)

    Note over AG,RK: Stage 5-6: Ranking & Itinerary
    AG->>RK: Invoke Ranking Agent with places metadata
    RK->>VX: Query Vertex AI for reasoning
    RK->>GO: calculate_route_distances (walking/driving duration)
    GO-->>RK: Distance matrices & route durations
    RK-->>BE: Yield ranking_itinerary state stream
    BE-->>FE: Stream Stage 5-6 progress updates (SSE)

    Note over AG,PV: Stage 7: Policy & Validation
    AG->>PV: Invoke Policy Agent
    PV->>VX: Query Vertex AI for policy compliance checks
    PV->>PV: Validate budget, check YMCA reciprocity, verify amenities
    PV-->>BE: Generate final markdown reports & constraints audits
    BE-->>FE: Yield policy_validation stream (SSE)
    FE->>FE: Parse markdown details & populate recommendation list
    FE->>User: Render Interactive Map Markers & Facility Detail Cards
```

---

## Deployment & Infrastructure Diagram

The deployment model utilizes fully managed serverless infrastructure on Google Cloud Platform (GCP) to deliver low latency, high availability, and secure secret configuration management:

```mermaid
graph TB
    subgraph Internet [Public Web Access]
        User[Traveler Browser]
    end

    subgraph GCP [Google Cloud Platform]
        subgraph FrontendRun [Cloud Run - Frontend Service]
            Nginx[Nginx Container]
            NginxConfig[entrypoint.sh Config generator]
        end

        subgraph BackendRun [Cloud Run - Backend Service]
            FastAPI[FastAPI Container]
            ADKCore[Google ADK Engine]
            FastAPIConfig[Lifespan Context]
        end

        subgraph IAM [IAM & Security]
            SA[Service Account: travelwell-cloudrun-sa]
        end

        subgraph APIs [Google APIs Integration]
            VertexAI[Vertex AI Platform]
            MapsPlatform[Google Maps Platform]
        end
    end

    User -->|HTTPS| Nginx
    Nginx -->|GET /config.json| NginxConfig
    NginxConfig -->|Read Backend URL| Nginx
    Nginx -->|POST /api/recommend| FastAPI
    FastAPI -->| Lifespan Init | FastAPIConfig
    FastAPIConfig -->| Run Agents | ADKCore
    ADKCore -->| Gemini Inference | VertexAI
    ADKCore -->| Places & Routes Queries | MapsPlatform
    FastAPI -->|GET /api/config| MapsPlatform
    SA -->|Authorize| BackendRun
    SA -->|Authorize| VertexAI

    style FrontendRun fill:#d4ebf2,stroke:#333,stroke-width:1px
    style BackendRun fill:#e8f0fe,stroke:#333,stroke-width:1px
    style APIs fill:#e6f4ea,stroke:#333,stroke-width:1px
```

---

## Agent Specifications & Technical Details

### 1. Research & Intelligence Agent
*   **System Role:** Discovery and data aggregator.
*   **Model Engine:** Vertex AI / Gemini.
*   **Ecosystem Tools:**
    *   `google_places_search`: Performs nearby searches for candidate gyms and fitness centers within travel radiuses.
    *   `fetch_facility_details`: Resolves operational details (website, phone, user reviews, opening hours, cost/rates, pools, showers, and treadmills).
*   **Key Behavior:** Evaluates raw text queries and geocodes partial landmarks, neighborhoods, or addresses. Preserves uncertainty by mapping missing values to `None`/`Unknown` rather than hallucinating prices or amenities.

### 2. Ranking & Itinerary Agent
*   **System Role:** Geographical filter and path planner.
*   **Model Engine:** Vertex AI / Gemini.
*   **Ecosystem Tools:**
    *   `google_maps_routes`: Queries routing tables to compute walking and driving coordinates, distances, and duration intervals between the traveler's coordinates and target venues.
*   **Key Behavior:** Calculates transit durations, applies proximity scores, and formats a list of travel recommendations based on distance limits.

### 3. Policy & Validation Agent
*   **System Role:** Decision compiler and compliance auditor.
*   **Model Engine:** Vertex AI / Gemini.
*   **Key Behavior:** Iterates deterministically over gym pricing, time windows, and user preferences. Handles logic checks:
    *   *YMCA Reciprocity Rule:* If the user has a YMCA membership and the facility name indicates YMCA, marks pricing access status as "free" with $0 guest pass requirements.
    *   *Budget Constraints Check:* Discards facilities with known guest pass rates above the user's budget.
    *   *Amenity Enforcement:* Double-checks mandatory amenities (showers/parking) and rates confidence statuses (*Excellent Match*, *Good Alternative*, *Limited Match*).

---

## Repository Project Layout

```
travelwell-ai/
├── README.md                   # Project overview, quickstart & feature list
├── .agents-cli-spec.md         # Google ADK CLI runtime configuration schema
├── docs/
│   ├── ARCHITECTURE.md         # Current file (Technical specification & diagrams)
│   ├── API_CONTRACTS.md        # REST endpoint specifications & schema payloads
│   └── PROJECT_CHARTER.md      # Strategic overview & target product milestones
├── backend/                    # Python FastAPI & Google ADK backend app
│   ├── app/
│   │   ├── app_utils/          # Core helpers, session registry & logging hooks
│   │   ├── services/           # Google Maps Geocoding, Places, and Routes wrappers
│   │   ├── tools/              # ADK tool definitions bound to Google APIs
│   │   ├── agent.py            # ADK agent cards, system prompts & sequential routes
│   │   └── fast_api_app.py     # FastAPI application and public REST /api/recommend endpoint
│   ├── tests/                  # Integration, unit, and rate-limit resilient tests
│   └── pyproject.toml          # Package configuration & UV dependency declarations
└── frontend/                   # React TypeScript frontend app
    ├── src/
    │   ├── api/
    │   │   └── client.ts       # SSE event-stream parser & REST endpoints connector
    │   ├── App.tsx             # Interactive dashboard, maps synchronizer & timeline tracker
    │   └── main.tsx
    ├── entrypoint.sh           # Dynamic container config.json generator
    └── package.json
```
