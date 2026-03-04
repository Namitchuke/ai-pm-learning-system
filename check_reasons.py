import sys
sys.path.insert(0, ".")
from app.clients.drive_client import read_json_file
data = read_json_file("pipeline_state.json")
slots = data.get("slots", {})
print("--- Slots Data ---")
for s, stats in slots.items():
    print(f"{s.upper()}: fetched={stats.get('articles_fetched')}, new={stats.get('articles_new')}, passed={stats.get('articles_passed')}, extracted={stats.get('articles_extracted')}, selected={stats.get('topics_selected')}")
print("--- Recent Discarded ---")
discarded = read_json_file("discarded.json").get("discarded", [])
counts = {}
for d in discarded[-50:]:
    counts[d.get("rejection_reason")] = counts.get(d.get("rejection_reason"), 0) + 1
print(counts)
print("--- Recent Errors ---")
errors = read_json_file("errors.json").get("errors", [])
print(errors[-1] if errors else "None")
