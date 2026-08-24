import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the FastAPI app
from app.fast_api_app import app

def test_recommend_endpoint_initialization_error():
    # Test that the recommend endpoint returns 500 JSON response on invalid input/session exception
    client = TestClient(app)
    # Sending invalid body format to trigger initialization exception
    response = client.post("/api/recommend", data="not json")
    assert response.status_code == 500
    data = response.json()
    assert "error_type" in data
    assert "stage" in data
    assert "message" in data

def test_resolve_location_endpoint():
    # Test resolve_location geocoding mock endpoint response
    client = TestClient(app)
    with patch("app.services.google_maps.geocode_address") as mock_geocode:
        mock_geocode.return_value = {
            "display_name": "Mock Gym Location, Chicago",
            "formatted_address": "Mock Address",
            "lat": 41.88,
            "lng": -87.63,
            "warning": None
        }
        response = client.get("/resolve_location?address=Chicago")
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Mock Gym Location, Chicago"
        assert data["lat"] == 41.88

def test_config_endpoint():
    # Test GET /api/config returns the maps API key
    client = TestClient(app)
    with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key-123"}):
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["mapsApiKey"] == "test-key-123"

def test_recommend_endpoint_success():
    mock_event = MagicMock()
    mock_event.author = "policy_validation"
    mock_event.content.role = "model"
    mock_event.content.parts = [MagicMock(text="### Recommendation Card: Life Time")]
    
    with patch("google.adk.runners.Runner.run") as mock_run:
        mock_run.return_value = [mock_event]
        
        with TestClient(app) as client:
            response = client.post("/api/recommend", json={
                "location": "Chicago",
                "timeWindow": "6:00 PM - 9:00 PM",
                "budgetSelection": "20",
                "hasYmca": False,
                "showersReq": False,
                "parkingReq": False,
                "poolPref": False,
                "treadmillPref": False
            })
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body_content = response.text
            assert "policy_validation" in body_content
            assert "Life Time" in body_content

def test_recommend_endpoint_returns_structured_recommendation():
    mock_event = MagicMock()
    mock_event.author = "policy_validation"
    mock_event.content.role = "model"
    markdown_payload = """
### Recommendation Card: Life Time Fitness
- Distance / Travel Time: 🚶 10 min
- Price: 💰 $20 Day Pass
- Place ID: mock_lifetime
- Address: 123 River North, Chicago
- Coordinates: [41.8962, -87.6287]
- Phone: (312) 555-0199
- Website: https://www.lifetime.life
- Google Maps URL: https://maps.google.com
- Eligibility Status: Fits Your Criteria
- Match Quality: Excellent Match

#### Constraint Satisfaction
- ✅ Budget ≤ $20
- ✅ Showers

#### Why this recommendation?
- **Satisfied Constraints:** Budget, Showers
- **Violated Constraints:** None
- **Recommendation Rationale:** Meets all traveler requirements.
"""
    mock_event.content.parts = [MagicMock(text=markdown_payload)]
    
    with patch("google.adk.runners.Runner.run") as mock_run:
        mock_run.return_value = [mock_event]
        
        with TestClient(app) as client:
            response = client.post("/api/recommend", json={
                "location": "Chicago",
                "timeWindow": "6:00 PM - 9:00 PM",
                "budgetSelection": "20",
                "hasYmca": False,
                "showersReq": True,
                "parkingReq": False,
                "poolPref": False,
                "treadmillPref": False
            })
            assert response.status_code == 200
            body_content = response.text
            
            final_result_line = None
            for line in body_content.split("\n"):
                if '"type": "result"' in line:
                    final_result_line = line
                    break
            
            assert final_result_line is not None
            import json
            raw_data = json.loads(final_result_line.replace("data: ", "").strip())
            
            assert raw_data["type"] == "result"
            assert "data" in raw_data
            data = raw_data["data"]
            assert len(data["recommendations"]) >= 1
            rec = data["recommendations"][0]
            assert rec["facility"]["name"] == "Life Time Fitness"
            assert rec["facility"]["pricing"]["cost"] == 20.0
            assert rec["eligibility_status"] == "Fits Your Criteria"


def test_recommend_pricing_reciprocity_and_safety():
    from app.fast_api_app import parse_markdown_to_recommendations
    
    # 1. YMCA member + YMCA facility => effective_price = 0
    markdown_ymca = """
Some introductory agent narrative text repeating prompt constraints.
### Recommendation Card: YMCA Loop Center
- Price: 💰 $25 Day Pass
- Distance: 🚶 10 min
- Coordinates: [41.89, -87.63]
"""
    recs_ymca = parse_markdown_to_recommendations(markdown_ymca, budget_sel="none", has_ymca=True)
    assert len(recs_ymca) == 1
    rec = recs_ymca[0]
    assert rec["facility"]["name"] == "YMCA Loop Center"
    assert rec["effective_price"] == 0.0
    assert rec["access_type"] == "membership_reciprocity"
    
    # 2. Free-only budget rejects paid non-YMCA facilities
    markdown_paid = """
### Recommendation Card: FFC Union Station
- Price: 💰 $20 Day Pass
- Distance: 🚶 15 min
"""
    recs_free_budget = parse_markdown_to_recommendations(markdown_paid, budget_sel="free", has_ymca=False)
    assert len(recs_free_budget) == 1
    assert recs_free_budget[0]["eligibility_status"] == "Rejected"
    
    # 3. Map popup and card show identical effective_price
    # Check effective_price at top level and facility pricing cost are equal
    assert recs_free_budget[0]["effective_price"] == recs_free_budget[0]["facility"]["pricing"]["cost"]
    
    # 4. Facility name is never replaced by agent narrative text (discards prefix prose cards[0])
    markdown_with_prefix = """
This is an introductory narrative repeating "I understand your requirements at Hotel Chicago..."
### Recommendation Card: Planet Fitness Chicago
- Price: 💰 $10 Day Pass
- Distance: 🚶 12 min
"""
    recs_with_prefix = parse_markdown_to_recommendations(markdown_with_prefix, budget_sel="20", has_ymca=False)
    assert len(recs_with_prefix) == 1
    # Check that name is the facility name, not the introductory prose
    assert recs_with_prefix[0]["facility"]["name"] == "Planet Fitness Chicago"
    
    # 5. Missing live Place Details fields do not crash the parser
    markdown_minimal = """
### Recommendation Card: Minimalist Gym
"""
    recs_minimal = parse_markdown_to_recommendations(markdown_minimal, budget_sel="none", has_ymca=False)
    assert len(recs_minimal) == 1
    # Verify address defaults to "Unknown Address", coords default to Chicago loop, phone defaults to "Unknown Phone"
    assert recs_minimal[0]["facility"]["address"] == "Address unavailable"
    assert recs_minimal[0]["facility"]["phone"] == "Unknown Phone"
    assert recs_minimal[0]["facility"]["coordinates"] == {"lat": 41.8817, "lng": -87.6278}
