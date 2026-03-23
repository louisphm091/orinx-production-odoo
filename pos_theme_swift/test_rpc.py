import urllib.request
import json
import uuid

url = "http://localhost:8081/jsonrpc"
data = {
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "service": "object",
        "method": "execute_kw",
        "args": [
            "routex",
            2,
            "admin",
            "pos.dashboard.swift",
            "get_employee_filter_options",
            []
        ]
    },
    "id": str(uuid.uuid4())
}

req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
try:
    response = urllib.request.urlopen(req)
    print(response.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
