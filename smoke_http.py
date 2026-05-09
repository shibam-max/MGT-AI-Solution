import httpx
import json

# Read contract
with open("../materials/contracts/contract_01_master_services_agreement.txt") as f:
    text = f.read()

# POST to extract endpoint
client = httpx.Client(timeout=120)
response = client.post(
    "http://localhost:8000/agent/extract",
    json={"document_id": "http_msa", "text": text, "hint": "contract:msa"}
)
data = response.json()
trace_id = data.get("trace_id")
conf = data.get("confidence")
sor_id = data.get("sor_id")

print(f"POST /agent/extract -> status={response.status_code} conf={conf} sor_id={sor_id} trace={trace_id}")

# GET events
if trace_id:
    events_response = client.get(f"http://localhost:8000/runs/{trace_id}/events")
    events = events_response.json()
    event_names = [event["name"] for event in events]
    print(event_names)

# GET dead-letter queue
dlq_response = client.get("http://localhost:8000/dead-letter")
dlq = dlq_response.json()
print(f"DLQ size={len(dlq)}")

client.close()
