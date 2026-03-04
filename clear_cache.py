import sys
import os
sys.path.insert(0, ".")
from app.clients.drive_client import read_json_file, write_json_file
cache = read_json_file("cache.json")
if cache and "processed_urls" in cache:
    print(f"Clearing {len(cache['processed_urls'])} urls from cache...")
    cache["processed_urls"] = {}
    write_json_file("cache.json", cache)
    print("Cache cleared successfully on Google Drive.")
else:
    print("Cache or processed_urls not found.")
