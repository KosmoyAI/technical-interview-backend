#!/usr/bin/env python3
import requests
import time
import pprint

BASE_URL = "http://localhost:8000"
PROMPT = "Hello, who are you?"

print("1️⃣  Creating job …")
res = requests.post(f"{BASE_URL}/jobs", json={"prompt": PROMPT})
res.raise_for_status()
job = res.json()
print("→", job)

print("2️⃣  Polling …")
while True:
    r = requests.get(f"{BASE_URL}/jobs/{job['job_id']}")
    r.raise_for_status()
    data = r.json()
    pprint.pp(data)
    if data["status"] in ("finished", "failed"):
        break
    time.sleep(1)

if data["status"] == "failed":
    print("Job failed — skipping streaming test.")
    exit(1)

SECOND_PROMPT = "Calculate (7-2)**3"

print("3️⃣  Streaming endpoint …")
with requests.post(
    f"{BASE_URL}/stream",
    json={"prompt": SECOND_PROMPT},
    stream=True,
) as r:
    for line in r.iter_lines():
        print(line.decode("utf-8"))

