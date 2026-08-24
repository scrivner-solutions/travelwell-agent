# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Dict, Any
from app.services.mock_data import load_mock_data

def calculate_route_distances(facility_id: str) -> Dict[str, Any]:
    """Calculates route walking times, driving times, and distances.

    Args:
        facility_id: The unique identifier for the facility.

    Returns:
        A dictionary containing walking time, driving time, and distance metrics.
    """
    from app.services.google_maps import get_maps_api_key, get_route_live, get_place_details_live
    key = get_maps_api_key()
    if key and not facility_id.startswith("mock_"):
        details = get_place_details_live(facility_id) or {}
        dest_coords = details.get("geometry", {}).get("location", {}) if details.get("geometry") else {}
        dest_lat = dest_coords.get("lat") or 41.8962 # River North area default
        dest_lng = dest_coords.get("lng") or -87.6287
        
        dest_str = f"{dest_lat},{dest_lng}"
        origin_str = "41.8817,-87.6278"
        walk_route = get_route_live(origin_str, dest_str, "walking")
        drive_route = get_route_live(origin_str, dest_str, "driving")
        
        walk_min = 15
        if walk_route and "duration_value_seconds" in walk_route:
            walk_min = max(1, int(walk_route["duration_value_seconds"] / 60))
        
        drive_min = 5
        if drive_route and "duration_value_seconds" in drive_route:
            drive_min = max(1, int(drive_route["duration_value_seconds"] / 60))
        
        dist_miles = 0.5
        if walk_route and "distance_text" in walk_route:
            try:
                dist_text = walk_route["distance_text"]
                cleaned_dist = "".join([c for c in dist_text if c.isdigit() or c == "."])
                dist_miles = float(cleaned_dist)
            except Exception:
                dist_miles = 0.5
        
        return {
            "status": "success",
            "travel_metadata": {
                "walk_minutes": walk_min,
                "drive_minutes": drive_min,
                "distance_miles": dist_miles
            }
        }

    data = load_mock_data()
    for scenario in data.get("scenarios", []):
        for fac in scenario.get("candidate_facilities_seed", []):
            if fac.get("id") == facility_id:
                return {
                    "status": "success",
                    "travel_metadata": fac.get("travel_metadata")
                }
    return {"status": "error", "message": f"Facility {facility_id} not found."}
