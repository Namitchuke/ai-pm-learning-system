import json
from app.clients import drive_client
import time

def fix():
    print("Reading sources...")
    sources = drive_client.read_json_file("rss_sources.json")
    if not sources:
        print("No sources found.")
        return
    
    modified = False
    for s in sources.get("sources", []):
        if "anthropic.com" in s.get("feed_url", "") or "pragmaticengineer.com" in s.get("feed_url", ""):
            if s.get("enabled", True):
                s["enabled"] = False
                print(f"Disabled {s['name']}")
                modified = True
                
    if modified:
        drive_client.write_json_file("rss_sources.json", sources)
        print("Updated rss_sources.json in Drive")
    else:
        print("Already disabled or not found.")

if __name__ == "__main__":
    fix()
