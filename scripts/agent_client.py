import os
from uuid import uuid4
import httpx


def main():
    key = os.environ["HUMANLOOP_API_KEY"]
    base = os.environ.get("HUMANLOOP_API_URL", "http://127.0.0.1:8000/api/v1")
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {key}"}, timeout=20, follow_redirects=False) as client:
        workers = client.get("/agent/workers", params={"q": "research"})
        workers.raise_for_status()
        print("Public profiles:", workers.json()["total"])
        draft = client.post("/agent/tasks/drafts", headers={"Idempotency-Key": str(uuid4())}, json={"title": "Check public store hours", "description": "Read publicly posted hours from a public entrance. No private access or purchase.", "category": "Retail checks", "city": "Toronto", "budget": 3000, "currency": "CAD"})
        draft.raise_for_status()
        print("Created draft:", draft.json()["id"], draft.json()["status"])
        print("No publication, assignment or payment occurred.")


if __name__ == "__main__":
    main()
