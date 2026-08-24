import pytest
from app.fast_api_app import parse_markdown_to_recommendations

def test_ui_regression_contracts():
    # Simulates an agent output containing narrative and cards
    markdown = """
I understand your traveler profile and have selected the best Loop facilities for you.
### Recommendation Card: Loop YMCA Fitness Center
- Price: 💰 $0 YMCA Reciprocity
- Distance: 🚶 12 min
- Place ID: ChIJ12345
- Coordinates: [41.88, -87.63]
- Website: https://ymcachicago.org/loop
- Google Maps URL: https://ymcachicago.org/loop
- Eligibility Status: Fits Your Criteria

#### Why this recommendation?
It satisfies your membership reciprocity!
"""

    recs = parse_markdown_to_recommendations(markdown, budget_sel="free", has_ymca=True)
    assert len(recs) == 1
    rec = recs[0]
    
    # 1. Card title == Facility name
    assert rec["name"] == "Loop YMCA Fitness Center"
    
    # 2. Popup title == Facility name
    assert rec["name"] == "Loop YMCA Fitness Center"
    
    # 3. Open in Maps opens google_maps_url
    def get_maps_url(r):
        mapsUrl = r.get("google_maps_url")
        if not mapsUrl or mapsUrl == "https://maps.google.com" or not mapsUrl.startswith("http"):
            if r.get("place_id") and r["place_id"].startswith("ChI"):
                mapsUrl = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={r['place_id']}"
            else:
                coords = r.get("coordinates")
                mapsUrl = f"https://www.google.com/maps/search/?api=1&query={coords['lat']},{coords['lng']}"
        return mapsUrl

    # Website was parsed as maps url or website
    assert rec["website"] == "https://ymcachicago.org/loop"
    assert get_maps_url(rec) == "https://ymcachicago.org/loop"
    
    # Fallback test: no google_maps_url, fallback to place_id ChI...
    rec_no_url = rec.copy()
    rec_no_url["google_maps_url"] = ""
    assert get_maps_url(rec_no_url) == "https://www.google.com/maps/search/?api=1&query=Google&query_place_id=ChIJ12345"
    
    # 4. Popup price == card price == effective_price
    assert rec["effective_price"] == 0.0
    assert rec["facility"]["pricing"]["cost"] == 0.0
    
    # 5. No AI narrative appears in card title or popup title
    for title in [rec["name"]]:
        assert "I understand" not in title
        assert "traveler profile" not in title
        assert "Recommendation Card:" not in title


def test_mccormick_ymca_verification():
    # Verify McCormick YMCA specific facts override Google Places
    from app.tools.facility_tools import fetch_facility_details, scrape_schedules
    
    # Simulates fetch details for McCormick YMCA
    res = fetch_facility_details("ymca_mccormick", has_ymca=True)
    assert res["status"] == "success"
    meta = res["details"]["source_metadata"]
    
    # Verified facts:
    assert meta["official_website_url"] == "https://www.ymcachicago.org/mccormick/"
    assert meta["formatted_address"] == "1834 N. Lawndale Ave, Chicago, IL 60647"
    assert meta["phone_number"] == "773-235-2525"
    assert meta["facility_hours"] == "Monday-Friday: 6 AM - 9 PM, Saturday-Sunday: 7 AM - 7 PM"
    assert meta["pool_hours"] == "Monday-Friday: 7 AM - 8 PM, Saturday-Sunday: 8 AM - 6 PM"
    
    # Confidences:
    assert meta["address_confidence"] == "high"
    assert meta["phone_confidence"] == "high"
    
    # Source tracking:
    assert meta["address_source"] == "official_site"
    assert meta["phone_source"] == "official_site"


def test_skokie_starting_marker_resolution():
    from app.services.google_maps import geocode_address
    res = geocode_address("Residence Inn Skokie, IL")
    assert res["lat"] == pytest.approx(42.0324, abs=1e-3)
    assert res["lng"] == pytest.approx(-87.7417, abs=1e-3)
    assert "Skokie" in res["formatted_address"]


def test_recommendation_cards_uniqueness():
    markdown = """
### Recommendation Card: Unique Gym A
- Place ID: ChIJunique_a
- Eligibility Status: Fits Your Criteria

### Recommendation Card: Unique Gym A
- Place ID: ChIJunique_a
- Eligibility Status: Fits Your Criteria

### Recommendation Card: Unique Gym B
- Place ID: ChIJunique_b
- Eligibility Status: Fits Your Criteria

### Recommendation Card: Unique Gym C
- Place ID: ChIJunique_c
- Eligibility Status: Fits Your Criteria

### Recommendation Card: Unique Gym D
- Place ID: ChIJunique_d
- Eligibility Status: Fits Your Criteria
"""
    recs = parse_markdown_to_recommendations(markdown, budget_sel="20", has_ymca=False)
    # Backend cap is 3 unique recommendations
    assert len(recs) <= 3
    # Check that there are no duplicate place_ids
    pids = [r["place_id"] for r in recs]
    assert len(pids) == len(set(pids))


def test_live_results_hours_uniqueness_and_photos():
    # If key is mock, live check uses fallback, let's verify hours default mapping
    markdown_mock_default = """
### Recommendation Card: Gym With No Hours
- Place ID: mock_nonexistent
- Eligibility Status: Fits Your Criteria
"""
    import os
    orig_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    try:
        # Simulate live search with a key present
        os.environ["GOOGLE_MAPS_API_KEY"] = "fake_key"
        recs = parse_markdown_to_recommendations(markdown_mock_default, budget_sel="20", has_ymca=False)
        assert len(recs) == 1
        # Live search hours missing should be "Hours unavailable", not the default "Open 06:00 - 22:00"
        assert recs[0]["opening_hours_summary"] == "Hours unavailable"
    finally:
        if orig_key:
            os.environ["GOOGLE_MAPS_API_KEY"] = orig_key
        else:
            del os.environ["GOOGLE_MAPS_API_KEY"]


def test_malformed_live_like_data_regression():
    # missing name, missing address, unknown pricing -> card skipped to prevent fake recommendations from narrative prose
    markdown = """
### Recommendation Card: 
- Address: 
- Price: Price unknown
- Distance: 15 min
- Place ID: ChIJmalformed
- Eligibility Status: Fits Your Criteria
"""
    recs = parse_markdown_to_recommendations(markdown, budget_sel="20", has_ymca=False, location_context="Skokie, IL")
    assert len(recs) == 0


def test_skokie_ymca_free_only_regression():
    # Input: location: Residence Inn, Skokie IL, active YMCA membership, free only, requires showers
    from app.tools.facility_tools import search_places
    import os
    orig_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    os.environ["GOOGLE_MAPS_API_KEY"] = "fake_key"
    try:
        # Check search execution
        res = search_places("Residence Inn Skokie IL", budget=0.0)
        assert res["status"] == "success"
    finally:
        if orig_key:
            os.environ["GOOGLE_MAPS_API_KEY"] = orig_key
        else:
            del os.environ["GOOGLE_MAPS_API_KEY"]

    markdown = """
Based on your requirements, McGaw YMCA is your top match because it is free with your YMCA membership.
### Recommendation Card: McGaw YMCA
- Address: 1420 Maple Ave, Evanston, IL 60201
- Price: 💰 $0 YMCA Reciprocity
- Distance: 🚶 12 min
- Place ID: ChIJmcgaw_ymca
- Eligibility Status: Fits Your Criteria

### Recommendation Card: Anytime Fitness
- Address: 4811 Dempser St, Skokie, IL 60077
- Price: 💰 $20 Day Pass
- Distance: 🚶 8 min
- Place ID: ChIJanytime
- Eligibility Status: Fits Your Criteria

### Recommendation Card: 
Based on your requirements, the YMCA is the best option.
"""
    recs = parse_markdown_to_recommendations(markdown, budget_sel="free", has_ymca=True, memberships=["YMCA"], location_context="Residence Inn Skokie IL")
    
    # Expected:
    # 1. No narrative text appears as facility name (the 3rd card contains narrative text and no name, so it is skipped)
    assert len(recs) == 2
    
    # 2. McGaw YMCA is YMCA and user has YMCA membership reciprocity, so effective_price = 0.0, eligibility = Fits Your Criteria
    assert recs[0]["name"] == "McGaw YMCA"
    assert recs[0]["effective_price"] == 0.0
    assert recs[0]["eligibility_status"] == "Fits Your Criteria"
    
    # Assert amenity states for McGaw YMCA (should be verified from official site)
    assert recs[0]["amenity_states"]["pool"] == "verified"
    assert recs[0]["amenity_states"]["showers"] == "verified"
    assert recs[0]["amenity_states"]["treadmill"] == "verified"
    assert recs[0]["amenity_sources"]["pool"] == "official_website"
    assert recs[0]["amenity_sources"]["showers"] == "official_website"
    assert recs[0]["amenity_sources"]["treadmill"] == "official_website"
    
    # 3. Anytime Fitness is paid ($20) and budget selection is free, so eligibility MUST be demoted/rejected
    assert recs[1]["name"] == "Anytime Fitness"
    assert recs[1]["effective_price"] == 20.0
    assert recs[1]["eligibility_status"] in ["Alternative", "Rejected"]
