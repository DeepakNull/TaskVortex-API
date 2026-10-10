async def test_signup_rejects_overlong_password(client):
    payload = {"name": "alex", "email": "alex@gmail.com", "password": "a" * 73}
    r = await client.post("/api/v1/users/signup", json=payload)
    assert r.status_code == 422


async def test_invalid_token_rejected(client):
    r = await client.get("/api/v1/tasks/history", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401