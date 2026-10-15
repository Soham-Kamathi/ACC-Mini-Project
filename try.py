import requests

resp = requests.post(
    "https://discourteously-unmanned-sanora.ngrok-free.dev/api/v1/f/065c12d0737c4cb6",
    headers={
        "X-API-Key": "fk_cKB9D-6GsstXEgvpzfBeiEY9tlLB946i76jBaqJbqKo",
        "ngrok-skip-browser-warning": "true",
    },
    json={"n": 20},
)
data = resp.json()
print("Result:", data.get("result", data))