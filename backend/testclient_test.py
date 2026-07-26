"""FastAPI TestClient API tests"""
import sys
sys.path.insert(0, r"d:\code\ai-fullstack-platform\backend")

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_openapi():
    print("1. GET /api/v1/openapi.json")
    r = client.get("/api/v1/openapi.json")
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        schema = r.json()
        print(f"   [OK] Valid JSON, {len(schema.get('paths', {}))} paths, "
              f"{len(schema.get('components', {}).get('schemas', {}))} schemas")
    else:
        print(f"   [FAIL] Body: {r.text[:300]}")

def test_login():
    print("\n2. POST /api/v1/login/access-token")
    r = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin@example.com", "password": "changethis"},
    )
    print(f"   Status: {r.status_code}")
    data = r.json()
    token = data.get("access_token", "")
    if token:
        print(f"   [OK] Token type: {data.get('token_type')}, len={len(token)}")
    else:
        print(f"   [FAIL] {data}")
    return token

def test_users_me(token):
    print("\n3. GET /api/v1/users/me")
    r = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"   [OK] email={data.get('email')}, "
              f"role={data.get('role')}, "
              f"active={data.get('is_active')}")
    else:
        print(f"   [FAIL] Body: {r.text[:200]}")

def test_signup():
    print("\n4. POST /api/v1/users/signup")
    r = client.post(
        "/api/v1/users/signup",
        json={
            "email": "testuser@example.com",
            "password": "testpassword123",
            "full_name": "Test User",
        },
    )
    print(f"   Status: {r.status_code}")
    if r.status_code in (200, 201):
        data = r.json()
        print(f"   [OK] email={data.get('email')}, id={data.get('id')}")
    else:
        print(f"   Body: {r.text[:200]}")

def test_docs_page():
    print("\n5. GET /docs (Swagger UI)")
    r = client.get("/docs")
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        print(f"   [OK] Content length: {len(r.text)}")
    else:
        print(f"   [FAIL] Status: {r.status_code}")

if __name__ == "__main__":
    print("=" * 60)
    print("API Smoke Test (TestClient)")
    print("=" * 60)
    test_openapi()
    token = test_login()
    if token:
        test_users_me(token)
    test_signup()
    test_docs_page()
    print("\nAll tests completed.")
