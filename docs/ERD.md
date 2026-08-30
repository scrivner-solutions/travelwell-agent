# Entity Relationship Diagrams

Generated from the live database by mermerd, restructured by domain for
readability. Regenerate after each migration (see the command at the bottom).

## Overview (all relationships, no columns)

```mermaid
erDiagram
    agent_events
    agent_runs
    calendar_events
    connected_sources
    notifications
    pending_actions
    places
    plan_item_options
    plan_items
    plans
    reservations
    trip_evidence
    trips
    user_preferences
    users
    wellness_windows
    agent_events }o--|| trips : "trip_id"
    agent_events }o--|| users : "user_id"
    agent_runs }o--|| agent_events : "trigger_event_id"
    agent_runs }o--|| trips : "trip_id"
    notifications }o--|| agent_runs : "run_id"
    plans }o--|| agent_runs : "generated_by_run_id"
    calendar_events }o--|| connected_sources : "source_id"
    calendar_events }o--|| trips : "trip_id"
    calendar_events }o--|| users : "user_id"
    connected_sources }o--|| users : "user_id"
    notifications }o--|| trips : "trip_id"
    notifications }o--|| users : "user_id"
    pending_actions }o--|| plan_items : "subject_item_id"
    pending_actions }o--|| trips : "trip_id"
    pending_actions }o--|| users : "user_id"
    plan_item_options }o--|| places : "place_id"
    reservations }o--|| places : "place_id"
    trips }o--|| places : "hotel_place_id"
    plan_item_options }o--|| plan_items : "item_id"
    plan_items }o--|| plans : "plan_id"
    plan_items }o--|| trips : "trip_id"
    plan_items }o--|| wellness_windows : "window_id"
    reservations }o--|| plan_items : "item_id"
    plans }o--|| trips : "trip_id"
    reservations }o--|| trips : "trip_id"
    trip_evidence }o--|| trips : "trip_id"
    trips }o--|| users : "user_id"
    wellness_windows }o--|| trips : "trip_id"
    user_preferences ||--|| users : "user_id"
```

## Identity and sources

```mermaid
erDiagram
    users {
        auth_provider auth_provider 
        timestamp_with_time_zone created_at 
        text display_name 
        citext email UK 
        text home_timezone 
        uuid user_id PK 
    }
    user_preferences {
        ARRAY activities 
        boolean allow_auto_book 
        boolean allow_calendar_write 
        ARRAY amenities 
        integer day_pass_budget_cents 
        ARRAY dietary 
        ARRAY memberships 
        smallint price_level_max 
        smallint session_max_minutes 
        smallint session_min_minutes 
        timestamp_with_time_zone updated_at 
        uuid user_id PK,FK 
        boolean watch_schedule 
    }
    connected_sources {
        timestamp_with_time_zone created_at 
        source_kind kind UK 
        timestamp_with_time_zone last_synced_at 
        ARRAY scopes 
        text secret_ref 
        uuid source_id PK 
        source_status status 
        uuid user_id FK,UK 
    }
    calendar_events {
        uuid cal_event_id PK 
        text content_hash 
        timestamp_with_time_zone ends_at 
        text external_id UK 
        timestamp_with_time_zone last_seen_at 
        text location 
        uuid source_id FK,UK 
        timestamp_with_time_zone starts_at 
        text status 
        text title 
        uuid trip_id FK 
        uuid user_id FK 
    }
    agent_events
    notifications
    pending_actions
    trips
    agent_events }o--|| users : "user_id"
    calendar_events }o--|| connected_sources : "source_id"
    calendar_events }o--|| trips : "trip_id"
    calendar_events }o--|| users : "user_id"
    connected_sources }o--|| users : "user_id"
    notifications }o--|| users : "user_id"
    pending_actions }o--|| users : "user_id"
    trips }o--|| users : "user_id"
    user_preferences ||--|| users : "user_id"
```

## Trip core

```mermaid
erDiagram
    trips {
        timestamp_with_time_zone activation_at 
        timestamp_with_time_zone created_at 
        text destination_city 
        double_precision destination_lat 
        double_precision destination_lng 
        text destination_region 
        real detection_confidence 
        date end_date 
        text hotel_address 
        double_precision hotel_lat 
        double_precision hotel_lng 
        text hotel_name 
        uuid hotel_place_id FK 
        text label 
        trip_origin origin 
        date start_date 
        trip_state state 
        text timezone 
        uuid trip_id PK 
        timestamp_with_time_zone updated_at 
        uuid user_id FK 
    }
    trip_evidence {
        timestamp_with_time_zone detected_at 
        uuid evidence_id PK 
        text kind 
        text source_label 
        text source_ref 
        text summary 
        uuid trip_id FK 
    }
    places {
        text address 
        ARRAY amenities 
        integer day_pass_cents 
        timestamp_with_time_zone fetched_at 
        jsonb hours 
        place_kind kind 
        double_precision lat 
        double_precision lng 
        text name 
        text photo_url 
        uuid place_id PK 
        smallint price_level 
        text provider_ref UK 
        reservation_provider reservable_via 
        text summary 
    }
    agent_events
    agent_runs
    calendar_events
    notifications
    pending_actions
    plan_item_options
    plan_items
    plans
    reservations
    users
    wellness_windows
    agent_events }o--|| trips : "trip_id"
    agent_runs }o--|| trips : "trip_id"
    calendar_events }o--|| trips : "trip_id"
    notifications }o--|| trips : "trip_id"
    pending_actions }o--|| trips : "trip_id"
    plan_item_options }o--|| places : "place_id"
    reservations }o--|| places : "place_id"
    trips }o--|| places : "hotel_place_id"
    plan_items }o--|| trips : "trip_id"
    plans }o--|| trips : "trip_id"
    reservations }o--|| trips : "trip_id"
    trip_evidence }o--|| trips : "trip_id"
    trips }o--|| users : "user_id"
    wellness_windows }o--|| trips : "trip_id"
```

## Planning

```mermaid
erDiagram
    plans {
        timestamp_with_time_zone created_at 
        uuid generated_by_run_id FK 
        text headline 
        uuid plan_id PK 
        text provenance_summary 
        plan_status status 
        uuid trip_id FK,UK 
        integer version UK 
    }
    wellness_windows {
        jsonb bounds 
        timestamp_with_time_zone computed_at 
        timestamp_with_time_zone ends_at 
        text gap_explanation 
        text label 
        date local_date 
        timestamp_with_time_zone starts_at 
        window_status status 
        uuid trip_id FK 
        uuid window_id PK 
    }
    plan_items {
        text calendar_event_ref 
        timestamp_with_time_zone created_at 
        uuid item_id PK 
        item_kind kind 
        boolean needs_reservation 
        uuid plan_id FK 
        timestamp_with_time_zone scheduled_end 
        timestamp_with_time_zone scheduled_start 
        item_status status 
        uuid trip_id FK 
        timestamp_with_time_zone updated_at 
        uuid window_id FK 
    }
    plan_item_options {
        text display_name 
        text display_summary 
        smallint distance_minutes 
        smallint duration_minutes 
        uuid item_id FK 
        ARRAY matched_preferences 
        uuid option_id PK 
        uuid place_id FK 
        smallint rank 
        text reason 
        text rejection_reason 
        option_state state 
    }
    reservations {
        text confirmation_code 
        timestamp_with_time_zone created_at 
        text external_url 
        text failure_reason 
        uuid item_id FK 
        smallint party_size 
        uuid place_id FK 
        reservation_provider provider 
        uuid reservation_id PK 
        timestamp_with_time_zone slot_at 
        reservation_status status 
        uuid trip_id FK 
        timestamp_with_time_zone updated_at 
    }
    agent_runs
    pending_actions
    places
    trips
    plans }o--|| agent_runs : "generated_by_run_id"
    pending_actions }o--|| plan_items : "subject_item_id"
    plan_item_options }o--|| places : "place_id"
    reservations }o--|| places : "place_id"
    plan_item_options }o--|| plan_items : "item_id"
    plan_items }o--|| plans : "plan_id"
    plan_items }o--|| trips : "trip_id"
    plan_items }o--|| wellness_windows : "window_id"
    reservations }o--|| plan_items : "item_id"
    plans }o--|| trips : "trip_id"
    reservations }o--|| trips : "trip_id"
    wellness_windows }o--|| trips : "trip_id"
```

## Agent spine, actions, notifications

```mermaid
erDiagram
    agent_events {
        event_disposition disposition 
        uuid event_id PK 
        event_kind kind 
        timestamp_with_time_zone occurred_at 
        jsonb payload 
        timestamp_with_time_zone received_at 
        uuid trip_id FK 
        uuid user_id FK 
    }
    agent_runs {
        jsonb context_snapshot 
        text error 
        timestamp_with_time_zone finished_at 
        run_kind kind 
        text model 
        jsonb result 
        uuid run_id PK 
        timestamp_with_time_zone started_at 
        run_status status 
        uuid trigger_event_id FK 
        uuid trip_id FK 
    }
    pending_actions {
        uuid action_id PK 
        boolean approval_required 
        timestamp_with_time_zone approved_at 
        timestamp_with_time_zone executed_at 
        jsonb execution_result 
        text idempotency_key UK 
        timestamp_with_time_zone proposed_at 
        jsonb proposed_payload 
        action_status status 
        uuid subject_item_id FK 
        uuid trip_id FK 
        action_type type 
        uuid user_id FK 
        jsonb verification 
    }
    notifications {
        text body 
        timestamp_with_time_zone created_at 
        jsonb cta 
        text kind 
        uuid notification_id PK 
        timestamp_with_time_zone opened_at 
        uuid run_id FK 
        timestamp_with_time_zone sent_at 
        notification_status status 
        text title 
        uuid trip_id FK 
        uuid user_id FK 
    }
    plan_items
    plans
    trips
    users
    agent_events }o--|| trips : "trip_id"
    agent_events }o--|| users : "user_id"
    agent_runs }o--|| agent_events : "trigger_event_id"
    agent_runs }o--|| trips : "trip_id"
    notifications }o--|| agent_runs : "run_id"
    plans }o--|| agent_runs : "generated_by_run_id"
    notifications }o--|| trips : "trip_id"
    notifications }o--|| users : "user_id"
    pending_actions }o--|| plan_items : "subject_item_id"
    pending_actions }o--|| trips : "trip_id"
    pending_actions }o--|| users : "user_id"
```

## Regenerating

```bash
go run github.com/KarnerTh/mermerd@latest \
  -c "postgresql://travelwell:travelwell@localhost:5432/travelwell" \
  -s public --useAllTables -e -o docs/ERD.md
```

Then restructure by domain (this file) and re-add the user_preferences to
users edge, which mermerd omits because the FK column is also the PK.
