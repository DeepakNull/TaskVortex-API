from tests.test_tasks import create


async def test_health_endpoint(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


async def test_metrics_count_ingested_heavy_tasks(client, auth_headers, mock_publish):
    before = (await client.get("/api/v1/metrics/health")).json()
    assert before["tasks_ingested"] == 0
    assert before["success_rate"] is None

    await create(client, auth_headers, complexity="heavy")

    after = (await client.get("/api/v1/metrics/health")).json()
    assert after["tasks_ingested"] == 1
    assert after["tasks_in_flight"] == 1