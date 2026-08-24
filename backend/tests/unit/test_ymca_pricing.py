import os
import sys

sys.path.insert(0, "/Users/olgascrivner/Documents/WTM Ambassador/Kaggle/travelwell-ai/backend")

from app.tools.facility_tools import fetch_facility_details

def test_ymca_pricing_rules():
    # Test 1: Active YMCA member + YMCA facility => free reciprocity
    res1 = fetch_facility_details("mock_chicago_ymca", has_ymca=True)
    pricing1 = res1["details"]["pricing"]
    assert pricing1["access_type"] == "membership_reciprocity"
    assert pricing1["cost"] == 0.0

    # Test 2: No YMCA membership + YMCA facility => no free reciprocity
    res2 = fetch_facility_details("mock_chicago_ymca", has_ymca=False)
    pricing2 = res2["details"]["pricing"]
    assert pricing2["access_type"] != "membership_reciprocity"
    assert pricing2["cost"] > 0.0

    # Test 3: Active YMCA member + non-YMCA facility => no reciprocity
    res3 = fetch_facility_details("mock_chicago_ffc", has_ymca=True)
    pricing3 = res3["details"]["pricing"]
    assert pricing3["access_type"] != "membership_reciprocity"
    assert pricing3["cost"] > 0.0

    print("All YMCA pricing unit tests passed!")

if __name__ == "__main__":
    test_ymca_pricing_rules()
