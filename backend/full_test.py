"""Full API test - starts server in background, tests all endpoints"""
import subprocess
import sys
import time
import httpx
import asyncio

async def run():
    # Start server
    print("Starting uvicorn on port 18005...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "18005"],
        cwd=r"d:\code\ai-fullstack-platform\backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for startup
    print("Waiting for startup (15s)...")
    time.sleep(15)
    
    # Check if process is alive
    if proc.poll() is not None:
        out, err = proc.communicate()
        print("SERVER DIED!")
        print("STDOUT:", out.decode("utf-8", errors="replace")[-1000:])
        print("STDERR:", err.decode("utf-8", errors="replace")[-1000:])
        return 1
    
    BASE = "http://127.0.0.1:18005/api/v1"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. OpenAPI
        print("\n" + "=" * 60)
        print("1. GET /openapi.json")
        try:
            r = await client.get(f"{BASE}/openapi.json")
            print(f"   Status: {r.status_code} ({len(r.text)} bytes)")
            if r.status_code == 200:
                schema = r.json()
                print(f"   ✅ Valid JSON, paths: {len(schema.get('paths', {}))}")
            else:
                print(f"   ❌ Body: {r.text[:200]}")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")

        # 2. Login
        print("\n" + "=" * 60)
        print("2. POST /login/access-token")
        try:
            r = await client.post(
                f"{BASE}/login/access-token",
                data={"username": "admin@example.com", "password": "changethis"},
            )
            print(f"   Status: {r.status_code}")
            data = r.json()
            token = data.get("access_token", "")
            print(f"   ✅ Token: {token[:40]}..." if token else f"   ❌ No token: {data}")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            token = ""

        # 3. Users/me
        if token:
            print("\n" + "=" * 60)
            print("3. GET /users/me")
            try:
                r = await client.get(
                    f"{BASE}/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                print(f"   Status: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    print(f"   ✅ User: email={data.get('email')}, role={data.get('role')}")
                else:
                    print(f"   ❌ Body: {r.text[:200]}")
            except Exception as e:
                print(f"   ❌ ERROR: {e}")

        # 4. Register
        print("\n" + "=" * 60)
        print("4. POST /users/signup")
        try:
            r = await client.post(
                f"{BASE}/users/signup",
                json={
                    "email": "test@example.com",
                    "password": "testpass123",
                    "full_name": "Test User",
                },
            )
            print(f"   Status: {r.status_code}")
            if r.status_code == 200 or r.status_code == 201:
                print(f"   ✅ Created: {r.json().get('email', '?')}")
            else:
                print(f"   Body: {r.text[:200]}")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")

    # Clean up
    print("\n" + "=" * 60)
    print("Stopping server...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("Server stopped.")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
