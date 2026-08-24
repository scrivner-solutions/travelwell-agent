import os
import requests
import math
from typing import Dict, Any, List

def get_maps_api_key() -> str:
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

def geocode_address(address: str) -> Dict[str, Any]:
    key = get_maps_api_key()
    if not key:
        if "skokie" in address.lower():
            return {
                "lat": 42.0324,
                "lng": -87.7417,
                "formatted_address": "Skokie, IL, USA",
                "display_name": "Skokie",
                "place_id": "mock_skokie",
                "warning": "Using mock location data fallback."
            }
        return {
            "lat": 41.8817,
            "lng": -87.6278,
            "formatted_address": "Downtown Chicago, IL, USA",
            "display_name": "Downtown Chicago",
            "place_id": "mock_chicago",
            "warning": "Using mock location data fallback."
        }
    
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(address)}&key={key}"
    status = "UNKNOWN_ERROR"
    err_msg = "Unknown error"
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "UNKNOWN_STATUS")
        err_msg = data.get("error_message", "No error message provided.")
        
        if status == "OK" and data.get("results"):
            result = data["results"][0]
            loc = result["geometry"]["location"]
            fmt_addr = result.get("formatted_address", address)
            place_id = result.get("place_id", "live_place")
            
            display_name = address
            if result.get("address_components"):
                display_name = result["address_components"][0].get("long_name", address)
                
            return {
                "lat": loc["lat"],
                "lng": loc["lng"],
                "formatted_address": fmt_addr,
                "display_name": display_name,
                "place_id": place_id,
                "warning": "Using best location match." if len(data["results"]) > 1 else None
            }
        else:
            print(f"Geocoding API status: {status}. Error message: {err_msg}")
    except Exception as e:
        print(f"Geocoding connection error: {e}")
        err_msg = str(e)
        
    # Try Places Text Search fallback if Geocoding API fails or returns ZERO_RESULTS
    print(f"Attempting Places search fallback for '{address}'...")
    fallback_res = geocode_via_places_fallback(address, key)
    if fallback_res:
        return fallback_res
        
    return {
        "lat": 41.8817,
        "lng": -87.6278,
        "formatted_address": address,
        "display_name": address,
        "place_id": "error_fallback",
        "warning": f"Geocoding failed (Google Status: {status}. Error: {err_msg}). Using default Loop coordinates."
    }

def geocode_via_places_fallback(address: str, key: str) -> Dict[str, Any]:
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={requests.utils.quote(address)}&key={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "UNKNOWN_STATUS")
        if status == "OK" and data.get("results"):
            result = data["results"][0]
            loc = result["geometry"]["location"]
            fmt_addr = result.get("formatted_address", address)
            place_id = result.get("place_id", "live_place")
            display_name = result.get("name", address)
            return {
                "lat": loc["lat"],
                "lng": loc["lng"],
                "formatted_address": fmt_addr,
                "display_name": display_name,
                "place_id": place_id,
                "warning": "Geocoding API failed. Resolved via Places Text Search fallback."
            }
        else:
            err_msg = data.get("error_message", "No details returned.")
            print(f"Places Fallback search failed. Status: {status}. Error: {err_msg}")
    except Exception as e:
        print(f"Places Fallback exception: {e}")
    return {}

def search_places_live(location_query: str, query_type: str = "gyms") -> List[Dict[str, Any]]:
    key = get_maps_api_key()
    if not key:
        return []
    
    if query_type == "ymca":
        query = f"YMCA near {location_query}"
    elif query_type == "skokie_ymca":
        query = f"YMCA Skokie IL"
    elif query_type == "mcgaw":
        query = f"McGaw YMCA"
    elif query_type == "evanston_ymca":
        query = f"YMCA Evanston"
    else:
        query = f"gyms and fitness centers in {location_query}"
        
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={requests.utils.quote(query)}&key={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") in ("OK", "ZERO_RESULTS"):
            results = data.get("results", [])
            places = []
            for item in results[:8]: # Take top 8 candidates to give more options
                places.append({
                    "place_id": item.get("place_id"),
                    "name": item.get("name"),
                    "formatted_address": item.get("formatted_address"),
                    "geometry": item.get("geometry", {}),
                    "rating": item.get("rating", 4.0),
                    "user_ratings_total": item.get("user_ratings_total", 0),
                    "photos": item.get("photos", [])
                })
            return places
    except Exception as e:
        print(f"Places Search error: {e}")
    return []

def get_place_details_live(place_id: str) -> Dict[str, Any]:
    key = get_maps_api_key()
    if not key:
        return {}
    
    fields = "name,formatted_address,geometry,rating,user_ratings_total,formatted_phone_number,website,url,opening_hours,photos"
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields={fields}&key={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "OK":
            return data.get("result", {})
    except Exception as e:
        print(f"Places Details error: {e}")
    return {}

def get_route_live(origin: str, destination: str, mode: str = "walking") -> Dict[str, Any]:
    key = get_maps_api_key()
    if not key:
        return {}
    
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={requests.utils.quote(origin)}&destinations={requests.utils.quote(destination)}&mode={mode}&key={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "OK" and data.get("rows"):
            elements = data["rows"][0].get("elements", [])
            if elements and elements[0].get("status") == "OK":
                elem = elements[0]
                return {
                    "distance_text": elem["distance"]["text"],
                    "distance_value_meters": elem["distance"]["value"],
                    "duration_text": elem["duration"]["text"],
                    "duration_value_seconds": elem["duration"]["value"]
                }
    except Exception as e:
        print(f"Distance Matrix API disabled or failed: {e}")
        
    # Math-based fallback calculation if Distance Matrix API is disabled on the GCP key
    try:
        orig_lat, orig_lng = map(float, origin.split(","))
        dest_lat, dest_lng = map(float, destination.split(","))
        
        # 1 degree of latitude in Chicago is ~69.0 miles.
        # 1 degree of longitude in Chicago is ~51.4 miles.
        dy = 69.0 * (dest_lat - orig_lat)
        dx = 51.4 * (dest_lng - orig_lng)
        dist_miles = math.sqrt(dx*dx + dy*dy)
        
        # Avoid 0.0 values
        dist_miles = max(0.1, dist_miles)
        dist_text = f"{dist_miles:.1f} mi"
        dist_meters = int(dist_miles * 1609.34)
        
        if mode == "walking":
            # Walk pace: 20 mins per mile
            duration_sec = max(60, int(dist_miles * 20 * 60))
            duration_text = f"{max(1, int(dist_miles * 20))} mins"
        else:
            # Driving pace: 4 mins per mile in downtown traffic
            duration_sec = max(60, int(dist_miles * 4 * 60))
            duration_text = f"{max(1, int(dist_miles * 4))} mins"
            
        return {
            "distance_text": dist_text,
            "distance_value_meters": dist_meters,
            "duration_text": duration_text,
            "duration_value_seconds": duration_sec
        }
    except Exception as ex:
        print(f"Math fallback routing computation failed: {ex}")
        
    return {}
