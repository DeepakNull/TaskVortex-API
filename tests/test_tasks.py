from uuid import uuid4

from app.core.redis import redis_client


def task_body(**overrides):
    body = {
        "title": "sample task",
        "description": "a task",
        "task_type": "web_scraping",
        "complexity": "light",
        "priority": 1,
        "payload": {"k": "v"},
    }
    body.update(overrides)
    return body


async def create(client, headers, **overrides):
    return await client.post("/api/v1/tasks", json=task_body(**overrides), headers=headers)


async def history_keys():
    return [k async for k in redis_client.scan_iter(match="task_history:*")]


# ---------- create ----------

async def test_create_light_task_completes_inline(client, auth_headers, mock_publish):
    r = await create(client, auth_headers)
    assert r.status_code == 201
    assert r.json()["status"] == "completed"
    mock_publish.assert_not_called()


async def test_create_heavy_task_is_queued_and_published(client, auth_headers, mock_publish):
    r = await create(client, auth_headers, complexity="heavy")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    mock_publish.assert_awaited_once()
    assert mock_publish.await_args.args[0]["task_id"] == body["task_id"]


async def test_create_requires_auth(client, mock_publish):
    r = await client.post("/api/v1/tasks", json=task_body())
    assert r.status_code == 401


async def test_create_validation_error_uses_custom_shape(client, auth_headers):
    body = task_body()
    del body["task_type"]
    r = await client.post("/api/v1/tasks", json=body, headers=auth_headers)
    assert r.status_code == 422
    data = r.json()
    assert data["success"] is False
    assert data["details"][0]["field"] == "task_type"


# ---------- get one ----------

async def test_get_own_task(client, auth_headers, mock_publish):
    created = (await create(client, auth_headers, complexity="heavy")).json()
    r = await client.get(f"/api/v1/tasks/{created['task_id']}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == created["task_id"]
    assert data["status"] == "queued"
    assert "user_id" not in data


async def test_cannot_read_another_users_task(client, make_headers):
    alice = await make_headers("alice@example.com")
    bob = await make_headers("bob@example.com")
    created = (await create(client, alice)).json()
    r = await client.get(f"/api/v1/tasks/{created['task_id']}", headers=bob)
    assert r.status_code == 404


async def test_unknown_task_returns_404(client, auth_headers):
    r = await client.get(f"/api/v1/tasks/{uuid4()}", headers=auth_headers)
    assert r.status_code == 404


# ---------- history ----------

async def test_history_pagination(client, auth_headers):
    for i in range(3):
        await create(client, auth_headers, title=f"task {i}")

    r = await client.get("/api/v1/tasks/history?page=1&limit=2", headers=auth_headers)
    data = r.json()
    assert len(data["tasks"]) == 2
    assert data["pagination"] == {"page": 1, "limit": 2, "total_count": 3, "total_pages": 2}

    r = await client.get("/api/v1/tasks/history?page=2&limit=2", headers=auth_headers)
    assert len(r.json()["tasks"]) == 1


async def test_history_filters_by_status(client, auth_headers, mock_publish):
    await create(client, auth_headers, complexity="light")
    await create(client, auth_headers, complexity="heavy")
    r = await client.get("/api/v1/tasks/history?status=queued", headers=auth_headers)
    assert [t["status"] for t in r.json()["tasks"]] == ["queued"]


async def test_history_search_by_title(client, auth_headers):
    await create(client, auth_headers, title="alpha report")
    await create(client, auth_headers, title="beta scrape")
    r = await client.get("/api/v1/tasks/history?search_query=alpha", headers=auth_headers)
    titles = [t["title"] for t in r.json()["tasks"]]
    assert titles == ["alpha report"]


async def test_history_accepts_timezone_aware_dates(client, auth_headers):
    await create(client, auth_headers)
    r = await client.get(
        "/api/v1/tasks/history",
        params={"start_date": "2000-01-01T00:00:00+05:30"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["pagination"]["total_count"] == 1


async def test_history_is_per_user(client, make_headers):
    alice = await make_headers("alice@example.com")
    bob = await make_headers("bob@example.com")
    await create(client, alice)
    r = await client.get("/api/v1/tasks/history", headers=bob)
    assert r.json()["pagination"]["total_count"] == 0


async def test_history_cache_is_populated_then_invalidated_by_writes(client, auth_headers):
    r = await client.get("/api/v1/tasks/history", headers=auth_headers)
    assert r.json()["pagination"]["total_count"] == 0
    assert len(await history_keys()) == 1  # cached

    await create(client, auth_headers)
    assert len(await history_keys()) == 0  # invalidated

    r = await client.get("/api/v1/tasks/history", headers=auth_headers)
    assert r.json()["pagination"]["total_count"] == 1


# ---------- update ----------

async def test_update_task(client, auth_headers):
    created = (await create(client, auth_headers)).json()
    r = await client.patch(
        f"/api/v1/tasks/{created['task_id']}", json={"title": "new title"}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["title"] == "new title"


async def test_update_rejects_null_title(client, auth_headers):
    created = (await create(client, auth_headers)).json()
    r = await client.patch(
        f"/api/v1/tasks/{created['task_id']}", json={"title": None}, headers=auth_headers
    )
    assert r.status_code == 422


async def test_update_allows_null_description(client, auth_headers):
    created = (await create(client, auth_headers)).json()
    r = await client.patch(
        f"/api/v1/tasks/{created['task_id']}", json={"description": None}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["description"] is None


async def test_update_with_empty_body_is_400(client, auth_headers):
    created = (await create(client, auth_headers)).json()
    r = await client.patch(f"/api/v1/tasks/{created['task_id']}", json={}, headers=auth_headers)
    assert r.status_code == 400


async def test_cannot_update_another_users_task(client, make_headers):
    alice = await make_headers("alice@example.com")
    bob = await make_headers("bob@example.com")
    created = (await create(client, alice)).json()
    r = await client.patch(
        f"/api/v1/tasks/{created['task_id']}", json={"title": "hijacked"}, headers=bob
    )
    assert r.status_code == 404