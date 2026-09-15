import asyncio
import httpx
from main import app

async def test_auth():
    print("Starting API tests...")
    
    # Use ASGITransport to test the app without running a separate server process
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Signup
        print("Testing Signup...")
        payload = {"username": "testuser", "password": "testpassword"}
        response = await client.post("/users/signup", json=payload)
        
        if response.status_code == 200:
            print("Signup Success!")
        elif response.status_code == 400 and "already registered" in response.text:
            print("User already exists, continuing...")
        else:
            print(f"Signup Failed: {response.status_code} - {response.text}")
            return

        # 2. Test Login
        print("Testing Login...")
        login_data = {"username": "testuser", "password": "testpassword"}
        response = await client.post("/users/login", data=login_data)
        
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"Login Success! Token: {token[:10]}...")
        else:
            print(f"Login Failed: {response.status_code} - {response.text}")
            return

        # 3. Test /users/me
        print("Testing /users/me...")
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.get("/users/me", headers=headers)
        if response.status_code == 200:
            print(f"Me Success! Username: {response.json().get('username')}")
        else:
            print(f"Me Failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    asyncio.run(test_auth())
