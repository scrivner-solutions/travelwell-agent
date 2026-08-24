# API Contracts & Data Models

This document defines the interface and data models shared between the React Frontend and the Google ADK Python Backend.

---

## REST Endpoints

### 1. Request Recommendations
* **URL:** `/api/recommend`
* **Method:** `POST`
* **Request Body:** `UserRequest`
* **Response:**
  ```json
  {
    "session_id": "session_8f3d4c2a",
    "status": "queued"
  }
  ```

### 2. Stream Agent Progress & Results
Streams execution status, logs, and final recommendations using Server-Sent Events (SSE).
* **URL:** `/api/events/{session_id}`
* **Method:** `GET`
* **Headers:** `Accept: text/event-stream`
* **Event Streams:**
  * **Event `trace`:** Emitted when a workflow stage progress changes. The frontend remains decoupled from backend agent implementation names and receives only logical progress stages.
    ```json
    {
      "stage": "Policy & Validation Layer",
      "status": "in_progress",
      "progress": 85,
      "message": "Enforcing budget, access, and schedule policies..."
    }
    ```
  * **Event `error`:** Emitted when a stage fails or the workflow encounters a system/API error.
    ```json
    {
      "stage": "Access & Membership",
      "error_code": "API_RATE_LIMIT",
      "message": "Places API limit exceeded. Falling back to mock dataset.",
      "fatal": false
    }
    ```
  * **Event `result`:** Emitted when the final itinerary and visualization data are ready.
    ```json
    {
      "status": "success",
      "data": {
        "trip_profile": { ... },
        "recommendations": [ ... ],
        "itinerary": [ ... ],
        "metadata": { ... }
      }
    }
    ```

---

## Data Models (JSON Schemas)

### `UserRequest`
```json
{
  "prompt": "I'll be in downtown Chicago tomorrow from 6-9 PM. I have a YMCA membership, but willing to pay up to $20. I prefer an indoor pool or treadmill, need showers.",
  "use_mock_data": true
}
```

### `Facility`
```json
{
  "id": "place_01",
  "name": "Downtown Chicago YMCA",
  "address": "30 S Michigan Ave, Chicago, IL 60603",
  "rating": 4.5,
  "amenities": ["indoor_pool", "treadmill", "showers", "lockers"],
  "emoji_badges": ["🏊", "🏃", "🚿", "🔒"],
  "pricing": {
    "access_type": "membership_reciprocity",
    "cost": 0.0,
    "pass_detail": "Free access with national YMCA membership"
  },
  "hours": {
    "open": "06:00",
    "close": "22:00",
    "warning": null
  },
  "distance": {
    "value_miles": 0.5,
    "walking_time_minutes": 10,
    "transit_time_minutes": 5,
    "description": "0.5 miles (10 min walk)"
  },
  "map_marker": {
    "lat": 41.8812,
    "lng": -87.6246,
    "label": "1",
    "title": "Downtown Chicago YMCA"
  },
  "reviews_summary": "Clean facility, but can get crowded between 5-7 PM.",
  "crowd_warning": "🔥 High crowd density expected during your visit window"
}
```

### `ItineraryItem`
```json
{
  "time_window": "06:00 PM - 06:15 PM",
  "activity": "Transit to Downtown Chicago YMCA",
  "duration_minutes": 15,
  "type": "transit",
  "details": "10-minute walk from hotel. 5-minute check-in buffer."
}
```

### `ConciergeResponse` (Final Data payload)
```json
{
  "trip_profile": {
    "location": "Downtown Chicago",
    "time_window": {
      "start": "2026-07-05T18:00:00",
      "end": "2026-07-05T21:00:00"
    },
    "budget": 20.0,
    "memberships": ["YMCA"],
    "preferences": ["indoor pool", "treadmill"],
    "required_amenities": ["showers"]
  },
  "recommendations": [
    {
      "facility": { ... },
      "rank": 1,
      "match_quality": "Excellent Match",
      "recommendation_reason": "Chosen because it is fully covered by your YMCA membership, has an indoor pool/treadmills, showers, and is a 10-minute walk from your location."
    }
  ],
  "itinerary": [
    { ... },
    {
      "time_window": "06:15 PM - 08:30 PM",
      "activity": "Workout at YMCA",
      "duration_minutes": 135,
      "type": "workout",
      "details": "Pool closes at 08:15 PM. Showers available on-site."
    },
    { ... }
  ],
  "metadata": {
    "data_mode": "mock",
    "sources_used": [
      "YMCA National Reciprocity Directory",
      "Google Places Database",
      "YMCA Facility Website"
    ],
    "generated_at": "2026-07-04T18:15:54-05:00"
  },
  "trace": [
    { "stage": "Trip Context", "status": "complete", "progress": 100, "message": "Parsed location, YMCA membership, $20 budget limit." },
    { "stage": "Fitness Discovery", "status": "complete", "progress": 100, "message": "Discovered 5 nearby fitness options." },
    { "stage": "Access & Membership", "status": "complete", "progress": 100, "message": "Validated YMCA reciprocity & day pass limits." },
    { "stage": "Facility Intelligence", "status": "complete", "progress": 100, "message": "Extracted indoor pool, shower details, and crowding warnings." },
    { "stage": "Ranking", "status": "complete", "progress": 100, "message": "Ranked YMCA #1, FFC Old Town #2, LA Fitness #3." },
    { "stage": "Itinerary", "status": "complete", "progress": 100, "message": "Created schedule with travel buffers." },
    { "stage": "Policy & Validation Layer", "status": "complete", "progress": 100, "message": "Enforced final quality policies." }
  ]
}
```
