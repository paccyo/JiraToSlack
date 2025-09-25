# Test velocity adapter function
import json

def adapt_velocity_data(vel):
    """Convert new velocity structure {history:[], avg:float, last_points:float} 
    to old structure {points:[], avgPoints:float} for backward compatibility"""
    if not vel:
        return None
    
    # If it's already old structure, return as-is
    if "points" in vel and "avgPoints" in vel:
        return vel
    
    # Convert new structure to old structure
    history = vel.get("history", [])
    avg = vel.get("avg", 0.0)
    
    # Convert history entries to old points format
    points = []
    for entry in history:
        points.append({
            "points": entry.get("points", 0.0),
            "name": entry.get("name", ""),
            "start": entry.get("start", ""),
            "end": entry.get("end", "")
        })
    
    return {
        "points": points,
        "avgPoints": avg
    }

# Test with new structure data
new_data = {
    "board": {"id": 1, "name": "SCRUM board"},
    "history": [
        {"id": 1, "name": "SCRUM スプリント 1", "start": "2025-09-17T08:53:35.977Z", "end": "2025-09-24T08:53:00.000Z", "points": 6.0, "metric": "parent_issues", "storyPointsRaw": 0.0},
        {"id": 34, "name": "SCRUM スプリント 2", "start": "2025-09-16T17:12:41.511Z", "end": "2025-09-24T08:53:00.000Z", "points": 1.0, "metric": "parent_issues", "storyPointsRaw": 0.0},
        {"id": 67, "name": "SCRUM スプリント 3", "start": "2025-09-24T01:44:40.393Z", "end": "2025-10-08T01:44:36.000Z", "points": 0.0, "metric": "subtasks_done", "storyPointsRaw": 0.0}
    ],
    "avg": 2.3333333333333335,
    "last_points": 6.0
}

# Test with old structure data  
old_data = {
    "points": [
        {"points": 6.0, "name": "Sprint 1"},
        {"points": 1.0, "name": "Sprint 2"},
        {"points": 0.0, "name": "Sprint 3"}
    ],
    "avgPoints": 2.33
}

print("Testing new structure:")
converted_new = adapt_velocity_data(new_data)
print(json.dumps(converted_new, indent=2, ensure_ascii=False))

print("\nTesting old structure (should pass through):")
converted_old = adapt_velocity_data(old_data)
print(json.dumps(converted_old, indent=2, ensure_ascii=False))

print("\nTesting None:")
converted_none = adapt_velocity_data(None)
print(converted_none)