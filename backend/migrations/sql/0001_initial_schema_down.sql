-- Reverses 0001_initial_schema.sql. CASCADE handles the two circular FK
-- chains (plans -> agent_runs, trips -> places) without ordering gymnastics.

drop table if exists notifications cascade;
drop table if exists agent_runs cascade;
drop table if exists agent_events cascade;
drop table if exists reservations cascade;
drop table if exists pending_actions cascade;
drop table if exists plan_item_options cascade;
drop table if exists plan_items cascade;
drop table if exists plans cascade;
drop table if exists wellness_windows cascade;
drop table if exists places cascade;
drop table if exists calendar_events cascade;
drop table if exists trip_evidence cascade;
drop table if exists trips cascade;
drop table if exists connected_sources cascade;
drop table if exists user_preferences cascade;
drop table if exists users cascade;

drop type if exists notification_status;
drop type if exists run_status;
drop type if exists run_kind;
drop type if exists event_disposition;
drop type if exists event_kind;
drop type if exists action_status;
drop type if exists action_type;
drop type if exists reservation_status;
drop type if exists reservation_provider;
drop type if exists option_state;
drop type if exists item_kind;
drop type if exists item_status;
drop type if exists plan_status;
drop type if exists window_status;
drop type if exists place_kind;
drop type if exists trip_origin;
drop type if exists trip_state;
drop type if exists source_status;
drop type if exists source_kind;
drop type if exists auth_provider;

-- Extensions (pgcrypto, citext) are left installed on purpose.
