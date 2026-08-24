import os
import json
from typing import Dict, Any

def load_mock_data() -> Dict[str, Any]:
    """Loads the deterministic evaluation and demo mock dataset from root-level tests/mock_data.json."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Resolve absolute path to tests/mock_data.json
    mock_file_path = os.path.abspath(os.path.join(current_dir, "../../../tests/mock_data.json"))
    
    if not os.path.exists(mock_file_path):
        raise FileNotFoundError(f"Mock data file not found at expected path: {mock_file_path}")
        
    with open(mock_file_path, "r", encoding="utf-8") as f:
        return json.load(f)
