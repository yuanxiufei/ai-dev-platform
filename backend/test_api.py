"""Quick API smoke test"""
import httpx
import json
import asyncio

BASE = "http://127.0.0.1:18003/api/v1"

async def run():
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. OpenAPI docs
        print("=" * 60)
        print("1. GET /openapi.json")
        try:
            r = await client.get(f"{BASE}/openapi.json")
            print(f"   Status: {r.status_code}")
            if r.status_code == 200:
                schema = r.json()
                print(f"   Valid JSON: YES, paths: {len(schema.get('paths', {}))}")
            else:
                print(f"   Body (first 500): {r.text[:500]}")
        except Exception as e:
            print(f"   ERROR: {e}")

        # 2. Login
        print("=" * 60)
        print("2. POST /login/access-token (admin@example.com / changethis)")
        try:
            r = await client.post(
                f"{BASE}/login/access-token",
                data={"username": "admin@example.com", "password": "changethis"},
            )
            print(f"   Status: {r.status_code}")
            data = r.json()
            token = data.get("access_token")
            print(f"   access_token: {token[:50]}..." if token else f"   FAIL: {data}")
        except Exception as e:
            print(f"   ERROR: {e}")
            token = None

        # 3. Users/me
        if token:
            print("=" * 60)
            print("3. GET /users/me (with token)")
            try:
                r = await client.get(
                    f"{BASE}/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                print(f"   Status: {r.status_code}")
                data = r.json()
                print(f"   User: email={data.get('email')}, role={data.get('role')}, id={data.get('id')}")
            except Exception as e:
                print(f"   ERROR: {e}")

        # 4. Health check
        print("=" * 60)
        print("4. GET /health (or /api/v1/)")
        try:
            r = await client.get("http://127.0.0.1:18003/api/v1/")
            print(f"   Status: {r.status_code}")
            print(f"   Body: {r.text[:200]}")
            # Try /health too
            r2 = await client.get("http://127.0.0.1:18003/health")
            print(f"   /health Status: {r2.status_code}, Body: {r2.text[:200]}")
        except Exception as e:
            print(f"   ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(run())
