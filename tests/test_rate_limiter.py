from app.core.config import settings
from app.core.rate_limiter import TokenBucket


def test_bucket_allows_until_capacity_then_blocks():
    bucket = TokenBucket(capacity=3, refill_rate=1, timestamp=0)
    assert [bucket.consume(0) for _ in range(4)] == [True, True, True, False]


def test_bucket_refills_over_time():
    bucket = TokenBucket(capacity=2, refill_rate=1, timestamp=0)
    bucket.consume(0)
    bucket.consume(0)
    assert bucket.consume(0) is False
    assert bucket.consume(1) is True


def test_bucket_refill_is_capped_at_capacity():
    bucket = TokenBucket(capacity=2, refill_rate=1, timestamp=0)
    bucket.consume(100)
    assert bucket.tokens == 1


async def test_middleware_returns_429_after_capacity(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_CAPACITY", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_REFILL_RATE", 0)
    codes = [(await client.get("/api/v1/metrics/health")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]