"""The plan read and the three item gates: accept, select-option, skip.

The concurrency branches follow test_trip_confirm's template (postcondition
first, then strict token mismatch), so those cases are spelled out per gate
rather than assumed from the trip tests.
"""

import pytest

pytestmark = pytest.mark.asyncio

STALE = "2020-01-01T00:00:00Z"


async def _plan(client, trip_id) -> dict:
    r = await client.get(f"/api/v1/trips/{trip_id}/plan")
    assert r.status_code == 200, r.text
    return r.json()


async def _item(client, trip_id, title) -> dict:
    plan = await _plan(client, trip_id)
    return next(i for i in plan["items"] if i["title"] == title)


# -- the read ---------------------------------------------------------------


async def test_plan_carries_items_with_their_live_options(authed_client, scene):
    plan = await _plan(authed_client, scene.trip_id)

    assert plan["version"] == 1
    assert plan["headline"] == "Room for 2 workouts and a dinner"
    # Declined items stay in the payload: the review flow shows what was
    # dropped, unlike /today and /timeline which hide them.
    assert {i["title"] for i in plan["items"]} == {
        "YMCA", "Beatrix", "Lakefront Trail", "Walk the Riverwalk"
    }

    workout = next(i for i in plan["items"] if i["title"] == "YMCA")
    # The card renders the selection plus its alternatives from one payload;
    # the rejected candidate is not offered here.
    assert [o["display_name"] for o in workout["options"]] == [
        "YMCA", "Hotel fitness room"
    ]
    assert workout["selected_option"]["display_name"] == "YMCA"


async def test_provenance_adds_the_rejected_candidates(authed_client, scene):
    workout = await _item(authed_client, scene.trip_id, "YMCA")

    r = await authed_client.get(f"/api/v1/plan-items/{workout['id']}/provenance")
    assert r.status_code == 200, r.text
    body = r.json()

    considered = {o["display_name"]: o for o in body["considered"]}
    assert set(considered) == {"YMCA", "Hotel fitness room", "Chicago Athletic Club"}
    ruled_out = considered["Chicago Athletic Club"]
    assert ruled_out["state"] == "rejected"
    assert ruled_out["rejection_reason"] == "11 minutes each way left you tight"
    # The opening the agent was filling, so "why here" is answerable too.
    assert body["window"]["label"] == "90 minutes free"


async def test_provenance_omits_the_window_for_an_item_that_fills_none(
    authed_client, scene
):
    """A dinner is placed against the day, not against a gap."""
    dinner = await _item(authed_client, scene.trip_id, "Beatrix")

    r = await authed_client.get(f"/api/v1/plan-items/{dinner['id']}/provenance")
    assert r.status_code == 200, r.text
    assert "window" not in r.json()


async def test_plan_404s_when_the_trip_has_none(authed_client, user, make_trip):
    trip = await make_trip(user)
    r = await authed_client.get(f"/api/v1/trips/{trip.trip_id}/plan")
    assert r.status_code == 404
    assert r.json()["code"] == "plan_not_found"


# -- accept -----------------------------------------------------------------


async def test_accept_moves_a_suggestion_into_the_plan(authed_client, scene):
    workout = await _item(authed_client, scene.trip_id, "YMCA")

    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/accept",
        json={"updated_at": workout["updated_at"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "planned"
    assert r.json()["updated_at"] != workout["updated_at"], "token must rotate"


async def test_accept_is_idempotent_and_survives_a_stale_retry(authed_client, scene):
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    first = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/accept",
        json={"updated_at": workout["updated_at"]},
    )
    token = first.json()["updated_at"]

    # The retry of a lost response still holds the pre-accept token.
    repeat = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/accept", json={"updated_at": STALE}
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["status"] == "planned"
    assert repeat.json()["updated_at"] == token, "a no-op must not rotate the token"


async def test_accept_with_a_stale_token_conflicts(authed_client, scene):
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/accept", json={"updated_at": STALE}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


async def test_accept_conflicts_once_the_item_is_declined(authed_client, scene):
    """Skipped is an answer already given; re-accepting is a different act."""
    hidden = await _item(authed_client, scene.trip_id, "Walk the Riverwalk")
    r = await authed_client.post(
        f"/api/v1/plan-items/{hidden['id']}/accept",
        json={"updated_at": hidden["updated_at"]},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_state"
    assert "skipped" in r.json()["detail"]


# -- select-option ----------------------------------------------------------


async def test_selecting_an_alternative_demotes_the_previous_choice(
    authed_client, scene
):
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    alternative = next(
        o for o in workout["options"] if o["display_name"] == "Hotel fitness room"
    )

    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/select-option",
        json={"option_id": alternative["id"], "updated_at": workout["updated_at"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["selected_option"]["display_name"] == "Hotel fitness room"
    assert body["title"] == "Hotel fitness room"
    # No data loss: the old choice is an alternative now, not gone.
    states = {o["display_name"]: o["state"] for o in body["options"]}
    assert states == {"YMCA": "alternative", "Hotel fitness room": "selected"}
    # Order is rank, so the card does not reshuffle under the user's finger.
    assert [o["display_name"] for o in body["options"]] == [
        "YMCA", "Hotel fitness room"
    ]


async def test_choosing_an_option_leaves_the_status_alone(authed_client, scene):
    """Picking a place is not accepting the suggestion: the review card lets
    someone swap and only then keep."""
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    alternative = next(
        o for o in workout["options"] if o["display_name"] == "Hotel fitness room"
    )

    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/select-option",
        json={"option_id": alternative["id"], "updated_at": workout["updated_at"]},
    )
    assert r.json()["status"] == "suggested"


async def test_reselecting_the_current_option_is_a_no_op(authed_client, scene):
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    current = workout["selected_option"]

    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/select-option",
        json={"option_id": current["id"], "updated_at": STALE},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] == workout["updated_at"]


async def test_a_rejected_option_cannot_be_selected(authed_client, scene):
    """422, not 409: refetching cannot make it selectable. Promoting it would
    clear the rejection_reason "Also considered" renders."""
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    prov = await authed_client.get(f"/api/v1/plan-items/{workout['id']}/provenance")
    rejected = next(
        o for o in prov.json()["considered"] if o["state"] == "rejected"
    )

    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/select-option",
        json={"option_id": rejected["id"], "updated_at": workout["updated_at"]},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "option_rejected"

    # And the reason it protects is still there afterwards.
    after = await authed_client.get(
        f"/api/v1/plan-items/{workout['id']}/provenance"
    )
    still = next(o for o in after.json()["considered"] if o["state"] == "rejected")
    assert still["rejection_reason"] == "11 minutes each way left you tight"


async def test_selecting_an_option_from_another_item_404s(authed_client, scene):
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    dinner = await _item(authed_client, scene.trip_id, "Beatrix")

    r = await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/select-option",
        json={
            "option_id": dinner["selected_option"]["id"],
            "updated_at": workout["updated_at"],
        },
    )
    assert r.status_code == 404
    assert r.json()["code"] == "option_not_found"


# -- skip -------------------------------------------------------------------


async def test_skip_declines_an_item(authed_client, scene):
    dinner = await _item(authed_client, scene.trip_id, "Beatrix")
    r = await authed_client.post(
        f"/api/v1/plan-items/{dinner['id']}/skip",
        json={"updated_at": dinner["updated_at"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "skipped"


async def test_remove_is_the_stronger_form_and_skipped_can_harden_into_it(
    authed_client, scene
):
    hidden = await _item(authed_client, scene.trip_id, "Walk the Riverwalk")
    r = await authed_client.post(
        f"/api/v1/plan-items/{hidden['id']}/skip",
        json={"updated_at": hidden["updated_at"], "remove": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "removed"


async def test_a_tombstone_cannot_be_downgraded_back_to_skipped(
    authed_client, scene
):
    hidden = await _item(authed_client, scene.trip_id, "Walk the Riverwalk")
    removed = await authed_client.post(
        f"/api/v1/plan-items/{hidden['id']}/skip",
        json={"updated_at": hidden["updated_at"], "remove": True},
    )

    r = await authed_client.post(
        f"/api/v1/plan-items/{hidden['id']}/skip",
        json={"updated_at": removed.json()["updated_at"]},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_state"


# -- plan rollup and ownership ----------------------------------------------


async def test_plan_status_tracks_the_items_it_holds(authed_client, scene):
    """Persisted and queried by list_trips, never rendered. Leaving it at
    `proposed` forever would be a lie the trip list reads."""
    plan = await _plan(authed_client, scene.trip_id)
    assert plan["status"] == "proposed"

    undecided = [i for i in plan["items"] if i["status"] in ("suggested", "awaiting_user")]
    first, *rest = undecided
    await authed_client.post(
        f"/api/v1/plan-items/{first['id']}/accept",
        json={"updated_at": first["updated_at"]},
    )
    assert (await _plan(authed_client, scene.trip_id))["status"] == "partially_accepted"

    for item in rest:
        await authed_client.post(
            f"/api/v1/plan-items/{item['id']}/accept",
            json={"updated_at": item["updated_at"]},
        )
    assert (await _plan(authed_client, scene.trip_id))["status"] == "accepted"


async def test_another_users_item_is_not_found(
    authed_client, scene, other_user, sign_in
):
    """Existence is private: the same 404 as a missing row."""
    item_id = (await _plan(authed_client, scene.trip_id))["items"][0]["id"]

    sign_in(authed_client, other_user)
    r = await authed_client.get(f"/api/v1/plan-items/{item_id}/provenance")
    assert r.status_code == 404
    assert r.json()["code"] == "item_not_found"


# -- the embedded window and the reservation flag ---------------------------


async def test_item_carries_its_opening_so_the_review_needs_one_request(
    authed_client, scene
):
    """The review card leads with the window, so it must ride on the item."""
    workout = await _item(authed_client, scene.trip_id, "YMCA")

    assert workout["window"]["label"] == "90 minutes free"
    assert workout["window"]["id"] == workout["window_id"]
    assert workout["window"]["bounds"], "the opening has to explain itself"

    # A dinner fills no gap, so the field is simply absent (exclude_none).
    dinner = await _item(authed_client, scene.trip_id, "Beatrix")
    assert "window" not in dinner


async def test_needs_reservation_rides_on_the_item(authed_client, scene):
    dinner = await _item(authed_client, scene.trip_id, "Beatrix")
    workout = await _item(authed_client, scene.trip_id, "YMCA")

    assert dinner["needs_reservation"] is True
    assert workout["needs_reservation"] is False


# -- accept all -------------------------------------------------------------


async def test_accept_all_answers_every_open_item(authed_client, scene):
    r = await authed_client.post(f"/api/v1/trips/{scene.trip_id}/plan/accept-all")
    assert r.status_code == 200, r.text
    plan = r.json()

    by_title = {i["title"]: i for i in plan["items"]}
    assert by_title["YMCA"]["status"] == "planned"
    # A reservation is a later gate, so accepting does not park it on the user.
    assert by_title["Beatrix"]["status"] == "planned"
    assert by_title["Lakefront Trail"]["status"] == "planned"
    # Already declined, and accept-all is not a way to undo that.
    assert by_title["Walk the Riverwalk"]["status"] == "skipped"
    assert plan["status"] == "accepted"


async def test_accept_all_is_idempotent(authed_client, scene):
    """No token to be stale with, so a repeat has to be a no-op, not a 409."""
    first = await authed_client.post(f"/api/v1/trips/{scene.trip_id}/plan/accept-all")
    stamps = {i["title"]: i["updated_at"] for i in first.json()["items"]}

    second = await authed_client.post(f"/api/v1/trips/{scene.trip_id}/plan/accept-all")
    assert second.status_code == 200
    assert {i["title"]: i["updated_at"] for i in second.json()["items"]} == stamps


async def test_accept_all_leaves_a_swapped_choice_alone(authed_client, scene):
    """Accepting answers the keep/skip gate; it must not re-pick the option."""
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    alt = next(o for o in workout["options"] if o["state"] == "alternative")
    await authed_client.post(
        f"/api/v1/plan-items/{workout['id']}/select-option",
        json={"updated_at": workout["updated_at"], "option_id": alt["id"]},
    )

    r = await authed_client.post(f"/api/v1/trips/{scene.trip_id}/plan/accept-all")
    kept = next(i for i in r.json()["items"] if i["id"] == workout["id"])
    assert kept["selected_option"]["display_name"] == "Hotel fitness room"
    assert kept["status"] == "planned"


async def test_accept_all_on_a_trip_with_no_plan_is_404(
    authed_client, user, make_trip
):
    trip = await make_trip(user)
    r = await authed_client.post(f"/api/v1/trips/{trip.trip_id}/plan/accept-all")
    assert r.status_code == 404
    assert r.json()["code"] == "plan_not_found"


# -- a finished trip --------------------------------------------------------


async def _end_trip(trip_id, state):
    """Move the scene's trip into a past state, as the agent runtime would."""
    from sqlalchemy import update

    from app.db import engine as db
    from app.db.models import Trip

    async with db.SessionFactory() as session:
        await session.execute(
            update(Trip).where(Trip.trip_id == trip_id).values(state=state)
        )
        await session.commit()


@pytest.mark.parametrize("state", ["completed", "archived"])
async def test_a_finished_trips_plan_refuses_every_gate(
    authed_client, scene, state
):
    """A past plan is a record, not a draft.

    `removed` is filtered out of the retrospective, so a removal here would
    delete the user's own history rather than edit a plan. The item's status
    cannot catch this on its own: a finished trip can still hold a `planned`
    item whose booking was refused.
    """
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    alt = next(o for o in workout["options"] if o["state"] == "alternative")
    await _end_trip(scene.trip_id, state)

    for path, body in (
        (f"/api/v1/plan-items/{workout['id']}/accept",
         {"updated_at": workout["updated_at"]}),
        (f"/api/v1/plan-items/{workout['id']}/skip",
         {"updated_at": workout["updated_at"]}),
        (f"/api/v1/plan-items/{workout['id']}/skip",
         {"updated_at": workout["updated_at"], "remove": True}),
        (f"/api/v1/plan-items/{workout['id']}/select-option",
         {"updated_at": workout["updated_at"], "option_id": alt["id"]}),
        (f"/api/v1/trips/{scene.trip_id}/plan/accept-all", None),
    ):
        r = await authed_client.post(path, json=body) if body else (
            await authed_client.post(path)
        )
        assert r.status_code == 409, f"{path}: {r.text}"
        assert r.json()["code"] == "trip_past"

    # Untouched by all of it.
    assert (await _item(authed_client, scene.trip_id, "YMCA"))["status"] == "suggested"


async def test_a_finished_trip_still_reads_and_explains(authed_client, scene):
    """The gate is on changing, not on looking: the retrospective exists to be
    read, and provenance is the only answer it has to "why was this here?"."""
    workout = await _item(authed_client, scene.trip_id, "YMCA")
    await _end_trip(scene.trip_id, "archived")

    assert (await _plan(authed_client, scene.trip_id))["items"]
    r = await authed_client.get(f"/api/v1/plan-items/{workout['id']}/provenance")
    assert r.status_code == 200, r.text
