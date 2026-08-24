from typing import List, Dict, Any
from .cards import STAGE_CARDS

class AgentRegistry:
    """Manages the registry of all logical agents and workflow stages for the UI trace."""
    
    @staticmethod
    def get_all_stages() -> List[Dict[str, Any]]:
        return STAGE_CARDS

    @staticmethod
    def get_stage_by_id(stage_id: str) -> Dict[str, Any]:
        for stage in STAGE_CARDS:
            if stage["id"] == stage_id:
                return stage
        raise KeyError(f"Stage ID '{stage_id}' not found in registry.")

    @staticmethod
    def get_stage_by_logical_name(name: str) -> Dict[str, Any]:
        for stage in STAGE_CARDS:
            if stage["logical_stage"] == name:
                return stage
        raise KeyError(f"Logical stage name '{name}' not found in registry.")
