"""Quick persistence test."""
from storage.history_manager import save_session, load_all, load_one

sid = save_session({
    "transcription": "Open Chrome and search machine learning",
    "stt": {"language": "en", "confidence": 97.5},
    "intent": {"name": "search_web", "confidence": 95.0},
    "entities": {"application": "chrome", "query": "machine learning"},
    "planner": {"steps": [{"tool": "open_browser", "args": {"browser": "chrome"}}]},
    "execution": [{"success": True, "tool": "open_browser", "message": "Opened Chrome"}],
    "speech": {"text": "Opening Chrome and searching for machine learning."},
})
print(f"Saved session: {sid}")

all_s = load_all()
print(f"Total sessions: {len(all_s)}")

s = load_one(sid)
print(f"Loaded transcript: {s['transcript']}")
print(f"Entities (type={type(s['entities']).__name__}): {s['entities']}")
print(f"Planner (type={type(s['planner_output']).__name__}): {s['planner_output']}")
print("PERSISTENCE TEST PASSED")
