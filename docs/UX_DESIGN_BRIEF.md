# TravelWell Product and UX Design Brief

## Purpose

Use this document as the design source of truth when redesigning TravelWell.

TravelWell is evolving from a functional AI wellness prototype into a **mobile-first, product-ready travel wellness agent**.

The redesign must preserve the identity and strongest elements of the existing TravelWell application while creating a much more polished consumer experience.

The goal is **not to create a new unrelated visual concept**.

Start from the current TravelWell app and repository, identify its existing design language, then evolve it into a coherent product system.

## 1. Product Vision

TravelWell is an AI agent that helps travelers maintain their wellness routines while away from home.

It understands:

- upcoming trips
- calendar commitments
- free time
- location
- hotel and itinerary
- wellness preferences
- restaurants and food preferences
- available activities
- reservations
- changes during the trip

It then helps the traveler **take action**, not merely generate recommendations.

The core loop is:

**Understand → Recommend → Decide → Act → Adapt**

TravelWell may:

- identify an upcoming trip
- analyze the traveler's schedule
- identify wellness windows
- find gyms, pools, walking routes, parks, activities, and restaurants
- rank options
- display options spatially on a map
- recommend a plan
- make online reservations after approval
- add approved activities to the calendar
- adapt when plans change
- respond to text or voice requests

## 2. Preserve the TravelWell Identity

Before designing new screens, inspect:

- the current deployed application
- repository styles
- typography
- colors
- map styling
- existing icons
- spacing
- cards
- buttons
- TravelWell branding

Extract reusable design tokens where possible.

### Do

- preserve recognizable TravelWell visual identity
- modernize and simplify it
- reuse successful visual elements
- create consistent reusable components
- design a small coherent design system

### Do Not

- invent an unrelated visual brand
- turn TravelWell into a generic AI dashboard
- make everything dark, neon, or futuristic just because AI is involved
- replace the map with text
- make chat the dominant visual element

The intelligence should primarily be visible through **what TravelWell does**.

## 3. Mobile First

The phone is the primary device.

Design for someone who may be:

- walking through an airport
- carrying luggage
- between meetings
- standing in a hotel lobby
- walking through an unfamiliar city
- checking the app with one hand
- making a decision quickly

Optimize for:

- strong hierarchy
- large touch targets
- minimal typing
- short text
- fast scanning
- thumb-friendly controls
- clear confirmations
- contextual actions
- immediate access to voice

Desktop should be a responsive extension of the mobile experience.

## 4. Travel Is the Organizing Context

TravelWell should revolve around a **Trip**.

Example:

### Chicago

**Aug 18-21**

Conference Trip

✓ Calendar connected  
✓ Hotel identified  
✓ Flight identified

**TravelWell activates Aug 11**

`View Trip`

The user should always understand:

- which trip TravelWell is working on
- what information TravelWell knows
- where that information came from
- whether TravelWell is preparing, active, or inactive

## 5. Trip Creation and Connection

A trip can enter TravelWell in several ways.

### Calendar detection

TravelWell identifies likely travel from the user's connected calendar.

Example:

**We found an upcoming trip**

Chicago  
Aug 18-21

Based on:

- flight event
- hotel reservation
- conference events

`Use This Trip`  
`Edit`

### Manual trip

The user can provide:

- destination
- dates
- hotel or approximate location
- optional itinerary

### Additional sources

Future versions may support itinerary, reservation, or email imports.

The UI must not make automatic inference feel mysterious.

Always show the user what TravelWell believes the trip information is and allow correction.

## 6. Recommended Navigation

Start with four primary areas:

### Today

What's happening now and what TravelWell recommends next.

### Trip

Trip overview, schedule, itinerary, calendar context, and plan.

### Explore

Map-first discovery.

### Agent

Natural-language interaction, including voice.

A persistent voice action may also appear outside the Agent screen.

## 7. Today Screen

Today should be the highest-value screen during an active trip.

Example:

### Chicago

**Day 2 of 4**

Conference Trip

8:00 AM  
Conference

12:00 PM  
Lunch

2:00 PM  
Workshop

**5:30 PM**
### 90 minutes free

TravelWell found a wellness opportunity.

**YMCA**

7 min walk  
Pool + treadmill  
Membership accepted

**Why this fits**
Fits between your workshop and dinner.

`Add to Plan`

Then:

### Dinner

**Beatrix**

Healthy American · $$  
5 min from YMCA  
Vegetarian options

7:30 PM available

`Reserve 7:30`  
`View on Map`

The screen should make TravelWell's reasoning understandable without displaying model reasoning.

## 8. Trip Screen

The Trip screen should combine itinerary and TravelWell planning.

Possible sections:

### Trip Summary

Chicago  
Aug 18-21

Hotel  
Conference  
Flight information

### Connected Context

✓ Google Calendar  
✓ Trip details  
✓ Hotel location

### Timeline

Existing commitments and TravelWell actions appear together.

Visually distinguish:

**Existing**

Calendar and itinerary commitments.

**Suggested**

TravelWell recommendations that have not been accepted.

**Confirmed**

Activities and reservations the user approved.

Example:

8:00 Conference

12:00 Lunch

2:00 Workshop

5:30 **TravelWell Suggested: YMCA**

7:30 **Confirmed: Beatrix**

## 9. Explore Screen

Explore should remain strongly map-oriented.

Support categories such as:

`Workout` `Food` `Outdoor` `Recovery`

Relevant places include:

- gyms
- pools
- parks
- walking routes
- running routes
- healthy restaurants
- wellness activities

Map pins and recommendation cards should remain synchronized.

The map should help tell the story of the plan.

Example:

**Hotel → YMCA → Restaurant → Hotel**

Travel time and geographic relationships are important to the recommendation.

## 10. Restaurant Experience

Restaurants are part of the TravelWell wellness experience, not a separate restaurant search feature.

Recommendations may consider:

- proximity
- schedule
- travel time
- dietary preferences
- wellness goals
- price
- hours
- reservation availability

Example:

### Dinner after your workout

**Beatrix**

Healthy American · $$

5 min walk from YMCA  
Vegetarian options

**7:30 PM available**

`Reserve 7:30`

`Other Times`

`View on Map`

## 11. Reservation UX

When an online reservation can be completed, provide a short action flow.

**Recommendation**

↓

**Available Times**

↓

**User Selection**

↓

**Confirmation**

↓

**Reservation Execution**

↓

**Success**

↓

**Add to Plan / Calendar**

Clearly distinguish:

### Reserve in TravelWell

TravelWell can execute the reservation.

### Continue to Reservation Site

The user needs to complete the process externally.

Never display a reservation as confirmed until confirmation is actually received.

## 12. Voice Is a First-Class Input

Voice should be available throughout the experience.

The user should be able to say:

> Find me dinner near the hotel.

> Something closer.

> I only have 40 minutes.

> Skip the gym tonight.

> Find somewhere with a pool.

> Move my workout to tomorrow morning.

Voice is **an input mechanism**, not a separate product.

Voice, text, and touch should lead to the same TravelWell actions.

### Preferred pattern

User taps microphone.

🎙️

> I'm exhausted. Skip the gym and find something healthy near the hotel.

TravelWell converts the request into structured actions.

Then display:

### Updated Plan

~~5:30 PM YMCA~~

6:00 PM  
**Beatrix**

0.2 mi from hotel

6:15 PM reservation available.

`Reserve 6:15`

The user should visually confirm consequential actions.

## 13. Persistent Voice Access

Explore a prominent microphone action available from most screens.

Possible pattern:

**Bottom navigation**

Today | Trip | **🎙️** | Explore | Agent

or a floating microphone action.

Do not force the user to navigate through several screens before speaking.

## 14. Agent Screen

The Agent screen is useful for open-ended requests but should not become a traditional chatbot interface.

Prefer:

**User request**

↓

**Structured TravelWell response**

↓

**Cards / Timeline / Map / Actions**

instead of:

**User message**

↓

**Large paragraph**

Suggested prompts may include:

- What's nearby?
- Find dinner
- Adjust my plan
- Find a shorter workout
- What do I have time for?
- Find something healthy

## 15. Agent Lifecycle Must Be Visible

TravelWell has several states.

### Upcoming

Trip identified but TravelWell has not started preparing.

### Preparing

TravelWell has activated before the trip.

Example:

**TravelWell is preparing your Chicago trip**

I found 3 wellness windows.

`Review Plan`

### Active

The user is currently traveling.

Example:

**TravelWell Active**

Chicago · Day 2 of 4

Watching your trip schedule for relevant changes.

### Needs Attention

Something requires user input.

Example:

**Your meeting now ends at 6:00 PM**

Your planned workout no longer fits.

`Review Alternatives`

### Completed

Trip has ended and is archived.

Design consistent indicators for these states.

## 16. Proactive Agent Interactions

TravelWell is not only reactive.

Example notification:

### Your schedule changed

Your workshop now ends at 6:00 PM.

The YMCA closes at 7:00 PM, so your original plan no longer fits.

**I found a 35-minute alternative 4 minutes from your hotel.**

`View Alternative`

This should feel useful, not intrusive.

## 17. Confirmation Model

TravelWell may recommend freely.

Actions with real-world consequences require clear approval unless a future user preference explicitly authorizes otherwise.

Examples:

### Low consequence

No confirmation needed:

- search
- ranking
- recommendations
- route comparison

### User approval expected

- adding calendar events
- modifying schedule
- making restaurant reservations
- canceling reservations
- inviting someone
- purchases
- payments

Confirmation screens should clearly state:

**What**

**When**

**Where**

**Cost**, if any

**Who**, if relevant

## 18. Recommendation Cards

Build reusable components across wellness and dining.

Every card should quickly answer:

1. What is it?
2. Why did TravelWell select it?
3. How far away is it?
4. Does it fit my schedule?
5. What can I do next?

Do not overload cards.

Use progressive disclosure.

## 19. TravelWell Explanation Style

Good:

**Fits your 90-minute opening**

**7-minute walk from your hotel**

**Matches your vegetarian preference**

**Pool open until 9 PM**

**Within your $20 budget**

Avoid:

“Based on an analysis of your preferences, TravelWell recommends this activity.”

Keep explanations human and specific.

## 20. Core Agent States

Create a consistent component language for:

- Suggested
- Needs Approval
- Working
- Confirmed
- Changed
- Failed
- Needs Attention

Example:

### Reservation

**Working...**

then

✓ **Confirmed**

Beatrix  
7:30 PM  
Party of 2

## 21. Loading and Waiting

Agent actions may take longer than normal UI operations.

Design purposeful progress states.

Instead of:

`Loading...`

prefer:

**Checking nearby wellness options...**

**Looking at your schedule...**

**Checking reservation availability...**

**Updating your plan...**

Do not fake completion.

## 22. Visual Personality

Target:

**Calm + Active + Premium + Trustworthy**

The application should feel appropriate for:

- travel
- wellness
- maps
- planning
- personal assistance

Avoid:

- enterprise dashboards
- dense tables
- giant AI chat windows
- excessive gradients
- neon AI aesthetics
- unnecessary glass effects
- large amounts of generated prose
- repeated “Powered by AI” treatment

## 23. Design Scenarios

Prototype complete workflows rather than isolated screens.

### Scenario A: Trip Detection

Calendar connected → trip detected → user reviews trip → TravelWell schedules activation.

### Scenario B: Pre-Trip Planning

Seven days before travel → TravelWell activates → identifies wellness windows → prepares recommendations → user reviews.

### Scenario C: Wellness Opportunity

Agent finds free time → recommends activity → user approves → activity enters Trip plan.

### Scenario D: Restaurant Reservation

Agent recommends restaurant → available times → user chooses → confirms → reservation appears in Trip.

### Scenario E: Voice Change

User speaks:

> I don't have time for this workout anymore.

TravelWell presents shorter alternatives.

### Scenario F: Calendar Change

Meeting changes → TravelWell detects conflict → recommends adjusted plan → asks for approval.

## 24. Initial ClaudeDesign Deliverables

Create:

1. TravelWell design token audit
2. Mobile information architecture
3. Navigation
4. Today screen
5. Trip screen
6. Explore/map screen
7. Agent + voice interaction
8. Wellness recommendation card
9. Restaurant recommendation card
10. Reservation flow
11. Trip detection flow
12. Pre-trip activation state
13. Active-trip state
14. Schedule-change intervention
15. Confirmation states
16. Loading, error, empty, and success states
17. Responsive desktop interpretation

## Final Product Test

For every screen ask:

**Can the traveler understand what's happening within five seconds?**

For every recommendation ask:

**Can the traveler take the next action in one or two obvious steps?**

For every agent action ask:

**Does the user understand what TravelWell knows, what it wants to do, and whether it has actually done it?**