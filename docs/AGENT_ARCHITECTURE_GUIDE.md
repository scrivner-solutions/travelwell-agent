# TravelWell Agent Architecture and Intern Development Guide

## Mission

TravelWell is evolving from a wellness recommendation prototype into an **event-driven travel wellness agent**.

The goal is not to build a chatbot.

The goal is to build an agent that:

1. understands an upcoming trip
2. activates before the trip
3. analyzes itinerary and calendar context
4. identifies wellness opportunities
5. recommends useful activities and restaurants
6. takes approved actions
7. remains available during the trip
8. reacts when relevant circumstances change
9. returns to an inactive state after the trip

The TravelWell agent should feel **persistent to the user without requiring a continuously running LLM**.

## 1. Start by Understanding What Already Exists

Before changing the architecture:

- clone and run the repository
- understand the frontend
- understand the backend
- locate the Vertex AI integration
- locate current map functionality
- identify APIs and external dependencies
- identify current Cloud Run services
- inspect service accounts and runtime configuration
- identify storage/state mechanisms
- inspect deployment configuration
- understand current recommendation flow

Be able to trace:

**User → Frontend → Backend → Vertex AI → Tools/Data → Response → UI**

Do not rebuild functionality that already works.

## 2. The Central Domain Object: Trip

TravelWell should organize its behavior around a first-class **Trip** entity.

Conceptually:

```text
Trip
├── trip_id
├── user_id
├── destination
├── start_time
├── end_time
├── timezone
├── hotel/location
├── itinerary
├── calendar_events
├── preferences
├── wellness_goals
├── restaurants/preferences
├── recommendations
├── reservations
├── planned_actions
└── lifecycle_state
```

Exact implementation can evolve.

The important architectural decision is:

**Agent state belongs to a Trip, not to a chat session.**

## 3. Trip Sources

TravelWell should eventually support several ways to create or enrich a Trip.

### Calendar

User connects a calendar.

TravelWell detects likely travel-related events.

### Manual Input

User creates a trip manually:

- city
- dates
- hotel/location
- optional itinerary

### Future Sources

Potential future sources:

- flight itinerary
- hotel reservation
- email
- reservation confirmation
- conference agenda

The architecture should allow new trip sources without coupling the entire application to one source.

## 4. Calendar Integration

Calendar serves two different purposes.

### A. Trip Discovery

Calendar information helps identify upcoming travel.

For example:

```text
Flight to Chicago
Hotel reservation
Conference Day 1
Conference Day 2
```

may collectively indicate a trip.

TravelWell should suggest the inferred Trip and allow the user to confirm or edit it.

### B. Schedule Context

Once the Trip exists, calendar events help TravelWell understand:

- commitments
- free periods
- schedule changes
- possible wellness windows
- conflicts

The agent should not treat every calendar event as equally relevant.

## 5. Agent Lifecycle

Model TravelWell as a lifecycle.

```text
DETECTED
   ↓
CONFIRMED
   ↓
UPCOMING
   ↓
PREPARING
   ↓
ACTIVE
   ↓
COMPLETED
   ↓
ARCHIVED
```

Possible secondary states:

```text
NEEDS_USER_INPUT
NEEDS_APPROVAL
ACTION_IN_PROGRESS
ACTION_FAILED
```

## 6. Seven-Day Activation Trigger

Initial target:

**Activate TravelWell approximately seven days before the trip begins.**

Conceptual workflow:

```text
Trip confirmed
     │
     ▼
Activation scheduled
     │
     ▼
T - 7 days
     │
     ▼
TravelWell wakes
     │
     ├── Load trip
     ├── Load calendar
     ├── Understand itinerary
     ├── Identify open windows
     ├── Identify location context
     ├── Find wellness opportunities
     ├── Find useful restaurant options
     └── Prepare initial plan
             │
             ▼
        Notify user
```

Do not interpret “wake up” as keeping an LLM instance running.

It should be an event that starts an agent workflow.

## 7. Event-Driven Standby

During the trip, TravelWell should be conceptually “on standby.”

Technically, the preferred model is:

```text
Event
   ↓
Trigger
   ↓
Determine relevant Trip
   ↓
Determine whether event matters
   ↓
Agent workflow if needed
   ↓
Potential recommendation/action
   ↓
Return to standby
```

The system should be idle when nothing relevant is happening.

## 8. Possible Agent Triggers

TravelWell should eventually respond to several trigger categories.

### Scheduled Trigger

Examples:

- seven days before trip
- morning during active trip
- shortly before a planned activity

### User Trigger

Examples:

- text request
- voice request
- button/action

### Calendar Trigger

Examples:

- meeting added
- event time changed
- event canceled
- new free window

### Trip Trigger

Examples:

- trip confirmed
- trip dates changed
- hotel changed

### Reservation Trigger

Examples:

- reservation confirmed
- reservation changed
- reservation canceled

### External Context Trigger

Possible future triggers:

- weather
- flight disruption
- venue availability
- location change

Do not implement everything immediately.

Design the event model so new trigger types can be added later.

## 9. Pub/Sub/Event Architecture

A useful architectural direction is to normalize incoming events.

Example:

```text
Calendar Change ─┐
Voice Request ───┤
Text Request ────┤
Scheduler ───────┤
Reservation ─────┤
                 ▼
          TravelWell Events
                 │
                 ▼
             Pub/Sub
                 │
                 ▼
        Trigger / Event Handler
                 │
                 ▼
          Trip Context Loader
                 │
                 ▼
            Agent Workflow
```

This keeps integrations from directly controlling agent behavior.

## 10. The Agent Should Receive Context, Not Raw Chaos

Before invoking the primary reasoning agent, create structured context.

Example:

```text
TripContext
├── current_time
├── destination
├── trip_day
├── hotel
├── upcoming_events
├── open_windows
├── wellness_preferences
├── dining_preferences
├── confirmed_actions
├── outstanding_suggestions
└── trigger
```

The agent should reason over relevant context rather than receiving the user's entire history or every available calendar event.

## 11. Trigger Classification

Every event does not need a large agent execution.

Example:

```text
Incoming Event
       │
       ▼
Is there an active/relevant Trip?
       │
     No ─────→ Stop
       │
      Yes
       ▼
Does this materially affect the Trip?
       │
     No ─────→ Stop
       │
      Yes
       ▼
Run appropriate workflow
```

This will matter for:

- cost
- latency
- reliability
- avoiding unnecessary notifications

## 12. Voice, Text, and UI Are Inputs to the Same Agent

Do not create separate business logic for voice.

Preferred architecture:

```text
VOICE ──► Speech/Input Adapter ─┐
                               │
TEXT ──────────────────────────┼──► Intent / Agent Layer
                               │
UI ACTION ─────────────────────┘
```

Then:

```text
Intent
  ↓
Trip Context
  ↓
Agent/Workflow
  ↓
Structured Result
  ↓
UI
```

Voice is simply another way to express user intent.

## 13. Voice UX Example

User says:

> I'm exhausted. Skip the gym and find something healthy near my hotel.

Potential structured interpretation:

```text
intent: MODIFY_PLAN

cancel_suggestion:
    workout

request:
    type: restaurant
    preference: healthy
    proximity: hotel
```

Agent result:

```text
PlanUpdate
├── removed_activity
├── recommended_restaurant
├── reservation_options
└── explanation
```

Frontend renders this as cards and actions.

Avoid returning only natural-language text.

## 14. Structured Agent Outputs

Whenever practical, agent workflows should return structured objects.

Examples:

### WellnessRecommendation

```text
place
activity_type
distance
travel_time
duration
price
schedule_fit
reason
map_location
action_options
```

### RestaurantRecommendation

```text
restaurant
cuisine
distance
price
dietary_fit
available_times
reservation_method
reason
map_location
```

### PlanChange

```text
current_activity
conflict
suggested_change
reason
approval_required
```

The frontend should not have to parse free-form model text to determine what happened.

## 15. Agent Actions

Separate **reasoning** from **execution**.

Example:

```text
Agent:
"I recommend reserving Beatrix at 7:30 PM."

        ↓

Action Proposal

        ↓

User Confirmation

        ↓

Reservation Tool

        ↓

Verified Result
```

The agent should not claim success merely because it decided that an action should occur.

## 16. Confirmation Boundary

Search and analysis may usually happen without confirmation.

External actions should require explicit approval unless future product settings deliberately authorize them.

Examples requiring approval:

- make reservation
- cancel reservation
- modify calendar
- invite another person
- purchase
- payment

Conceptually:

```text
THINK
 ↓
PROPOSE
 ↓
CONFIRM
 ↓
EXECUTE
 ↓
VERIFY
 ↓
REPORT
```

This should become a core TravelWell workflow pattern.

## 17. Calendar Action Example

TravelWell identifies:

```text
5:30-7:00 PM free
```

Agent recommends:

```text
YMCA
5:40-6:45 PM
```

User selects:

`Add to Plan`

TravelWell may then:

1. create TravelWell plan item
2. ask whether to add to calendar if needed
3. create calendar event
4. verify calendar operation succeeded
5. update Trip state
6. show confirmation

## 18. Restaurant Reservation Example

```text
Free time detected
       ↓
Restaurant search
       ↓
Rank options
       ↓
Check reservation availability
       ↓
Show available time
       ↓
User selects
       ↓
Confirmation
       ↓
Reservation action
       ↓
Verify
       ↓
Save reservation
       ↓
Update Trip
       ↓
Optionally update calendar
```

If TravelWell cannot make the reservation directly, provide the external online reservation path instead.

Do not represent an external link as a completed reservation.

## 19. Schedule Change Example

Original plan:

```text
Workshop ends 5:00
Workout 5:30-6:45
Dinner 7:30
```

Calendar event changes:

```text
Workshop ends 6:00
```

Workflow:

```text
Calendar event
     ↓
Trip affected?
     ↓ YES
Existing plan conflict?
     ↓ YES
Find alternatives
     ↓
Agent proposes:
35-minute workout closer to hotel
     ↓
Notify user
```

This is one of TravelWell's strongest future agent capabilities.

## 20. Tool Architecture

Agent capabilities may eventually include:

```text
Calendar Tool
Map/Places Tool
Wellness Search Tool
Restaurant Search Tool
Reservation Tool
Weather Tool
Notification Tool
Trip Store
User Preference Store
```

These capabilities may be exposed using:

- APIs
- MCP
- A2A
- direct application services

Do not adopt a protocol simply because it is fashionable.

Choose the simplest reliable interface for each capability.

## 21. A2A

A2A becomes useful when TravelWell delegates work to another autonomous agent.

Example:

```text
TravelWell Orchestrator
       │
       ├──► Wellness Agent
       │
       ├──► Dining Agent
       │
       └──► Reservation Agent
```

Do not split into many agents prematurely.

First establish clear capability boundaries.

## 22. MCP

MCP may be useful for exposing reusable tools and external capabilities.

Potential examples:

```text
Google Calendar MCP
Places MCP
Restaurant MCP
Travel MCP
```

Again, start from product requirements.

MCP is an implementation interface, not the architecture itself.

## 23. Agent Orchestrator

As TravelWell grows, consider one coordinating agent/workflow.

Conceptually:

```text
               TravelWell Orchestrator
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
       Schedule       Wellness      Dining
       Context        Search        Search
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                    Plan Builder
                        │
                        ▼
                  Action Proposal
                        │
                        ▼
                  User Confirmation
                        │
                        ▼
                   Action Tools
```

The orchestrator owns the Trip-level objective.

Tools or specialized agents perform bounded capabilities.

## 24. Persistent State

Do not rely on model conversational memory as the source of truth.

Important state should live in application storage.

Examples:

```text
Trip
UserPreferences
CalendarContext
TravelWellPlan
Recommendation
Reservation
PendingAction
ActionResult
TriggerHistory
```

The agent should reconstruct relevant context from persisted state whenever it wakes.

## 25. Pending Actions

A useful concept is a durable `PendingAction`.

Example:

```text
PendingAction
├── action_id
├── trip_id
├── type
├── proposed_payload
├── created_at
├── approval_required
├── status
└── execution_result
```

Possible states:

```text
PROPOSED
APPROVED
EXECUTING
COMPLETED
FAILED
CANCELED
```

This makes agent actions auditable and recoverable.

## 26. Avoid Hidden Agent Behavior

The user should know:

- why TravelWell activated
- which Trip it is working on
- what changed
- what it recommends
- what requires approval
- which action is running
- whether the action succeeded

The frontend should expose those states clearly.

## 27. Notifications

TravelWell should notify only when there is meaningful value.

Good notification:

**Your afternoon schedule changed**

Your planned workout no longer fits.

I found a 35-minute alternative near your hotel.

`Review`

Bad notification:

**TravelWell has new recommendations!**

Avoid noisy agent behavior.

## 28. Seven-Day Pre-Trip Workflow MVP

The first proactive workflow should be intentionally bounded.

At T - 7 days:

1. load confirmed Trip
2. load relevant calendar events
3. identify major commitments
4. calculate obvious open windows
5. identify destination/hotel location
6. search a limited set of wellness options
7. optionally identify restaurant opportunities
8. generate an initial TravelWell plan
9. save recommendations
10. notify user that the plan is ready

This is enough to prove the proactive agent model.

## 29. During-Trip MVP

During an active Trip, support:

### User-triggered

- text request
- voice request
- card/button action

### Event-triggered

Start with only one or two high-value triggers.

Best initial candidate:

**calendar schedule change affecting an existing TravelWell plan**

This gives us a very strong demonstration of adaptation without building every possible trigger.

## 30. Product Architecture Principle

Keep these layers distinct:

```text
INPUTS
Calendar / Voice / Text / UI / Scheduler

        ↓

EVENT + TRIGGER LAYER

        ↓

TRIP CONTEXT

        ↓

ORCHESTRATION / AGENT

        ↓

CAPABILITIES
Search / Maps / Calendar / Reservations / etc.

        ↓

ACTION / CONFIRMATION

        ↓

PERSISTED STATE

        ↓

USER EXPERIENCE
Cards / Map / Timeline / Voice / Notifications
```

Do not mix all of these responsibilities into one giant agent prompt.

## 31. Reliability Principle

For every external action:

```text
Request
 ↓
Execute
 ↓
Observe result
 ↓
Verify
 ↓
Persist
 ↓
Display
```

Never assume that because an API/tool was called, the action succeeded.

## 32. Observability

The intern should be able to trace an agent activation.

Useful identifiers:

```text
trip_id
trigger_id
workflow_id
action_id
```

Example trace:

```text
calendar event changed
trigger accepted
trip loaded
conflict detected
agent invoked
alternative generated
notification created
user approved
calendar updated
action verified
```

This will become essential as TravelWell becomes more autonomous.

## 33. Safety and Permissions

Intern development access and runtime access should remain separated.

Human developer:

- builds services
- deploys Cloud Run
- works with Vertex AI
- works with Pub/Sub
- tests integrations

Runtime service accounts:

- access only required application resources
- access required secrets
- execute approved tools

Do not put production credentials into:

- frontend code
- repository
- prompts
- local configuration committed to Git

Do not expand IAM just to make an error disappear.

## 34. Initial Implementation Milestones

### M1: Understand Existing TravelWell

Deliver architecture map and successful local/deployed workflow.

### M2: Trip Model

Establish Trip as the central application object.

### M3: Calendar Connection

Retrieve relevant calendar information and associate it with Trip context.

### M4: Mobile Product Shell

Integrate the redesigned Today, Trip, Explore, and Agent surfaces.

### M5: Voice Input

Voice request enters the same intent/agent pipeline as text.

### M6: Pre-Trip Trigger

Implement T - 7 day activation for confirmed trips.

### M7: Initial Plan

Generate and persist wellness/dining recommendations using trip/calendar context.

### M8: Action Workflow

Implement:

**Propose → Confirm → Execute → Verify**

for at least one real action.

Strong candidates:

- calendar event
- restaurant reservation

### M9: Active Trip

Trip enters ACTIVE state and responds to user requests.

### M10: Reactive Trigger

Handle one meaningful schedule-change scenario.

## 35. What Not to Build Yet

Avoid premature complexity.

Do not begin by building:

- dozens of microservices
- five different agents
- autonomous payments
- every travel provider
- continuous location tracking
- complex multi-agent orchestration
- dozens of trigger types
- voice-only interfaces

Prove the TravelWell lifecycle first.

## 36. The Core Demo Story

A strong end-to-end TravelWell scenario should eventually look like this:

### 1. Trip detected

TravelWell sees an upcoming Chicago trip.

### 2. User confirms

`Use This Trip`

### 3. T - 7 days

TravelWell activates automatically.

### 4. Context assembled

Calendar + itinerary + hotel + preferences.

### 5. Initial plan

TravelWell identifies wellness windows and useful dining options.

### 6. During trip

User says:

> Find me a healthy dinner after my workout.

### 7. Agent responds

Restaurant + map + available reservation.

### 8. User confirms

`Reserve 7:30`

### 9. Action executes

Reservation confirmed and added to Trip.

### 10. Schedule changes

Meeting runs late.

### 11. TravelWell wakes

It recognizes the existing plan is no longer feasible.

### 12. Agent adapts

TravelWell proposes a shorter workout nearby.

### 13. User approves

Trip plan updates.

That is the product we are building.

## Final Engineering Test

For every new feature ask:

**What triggered this workflow?**

**Which Trip does it belong to?**

**What context does the agent actually need?**

**Is this reasoning or an external action?**

**Does the action need approval?**

**How do we verify success?**

**What persistent state changes?**

**What does the user see?**

If those questions have clear answers, the feature belongs cleanly in the TravelWell architecture.