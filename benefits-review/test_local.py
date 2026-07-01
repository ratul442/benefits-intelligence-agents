"""Quick local pipeline test."""
import json
import requests

company = open(r'..\..\data\sample\BDP_Company__PROFILE.md', encoding='utf-8').read()
market = open(r'..\..\data\sample\BDP_Market__PROFILE.md', encoding='utf-8').read()

payload = {'company_payload': company, 'market_payload': market, 'country': 'SGP'}
resp = requests.post('http://localhost:8088/invocations', json=payload, timeout=120)

print(f"HTTP Status: {resp.status_code}")

# Parse SSE events
for line in resp.text.split('\n'):
    if not line.startswith('data: '):
        continue
    data = json.loads(line[6:])
    if data['type'] == 'done':
        result = data['result']
        print(f"Pipeline Status: {result['status']}")
        print(f"Rows: {len(result['report']['rows'])}")
        meta = result['metadata']
        print(f"Total tokens: {meta['total_tokens']}")
        print(f"Total time: {meta['processing_time_ms']}ms")
        print(f"Topics: {len(meta['per_topic_timing'])}")
        for row in result['report']['rows'][:3]:
            print(f"  {row['comparison_key']}: company={row['company_provision'][:40]}, alignment={row['market_alignment']}")
        break
    elif data['type'] == 'error':
        print(f"ERROR: {data['message']}")
        break
