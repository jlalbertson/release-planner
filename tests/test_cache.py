"""Tests for the TTL-based in-memory cache.

Verifies:
- Basic get/put operations
- TTL expiry
- Invalidation
- Thread safety (basic concurrent access)
"""

from __future__ import annotations

import threading
import time

from release_planner import cache


class TestCacheBasicOperations:
    """Test basic get/put operations."""

    def setup_method(self):
        cache.clear()

    def test_get_returns_none_for_missing_key(self):
        assert cache.get("nonexistent", ttl=900) is None

    def test_put_and_get(self):
        cache.put("key1", {"data": "value"})
        result = cache.get("key1", ttl=900)
        assert result == {"data": "value"}

    def test_put_overwrites_existing(self):
        cache.put("key1", "old")
        cache.put("key1", "new")
        assert cache.get("key1", ttl=900) == "new"

    def test_get_different_keys(self):
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get("a", ttl=900) == 1
        assert cache.get("b", ttl=900) == 2

    def test_put_various_types(self):
        cache.put("str", "hello")
        cache.put("int", 42)
        cache.put("list", [1, 2, 3])
        cache.put("dict", {"a": 1})
        assert cache.get("str", ttl=900) == "hello"
        assert cache.get("int", ttl=900) == 42
        assert cache.get("list", ttl=900) == [1, 2, 3]
        assert cache.get("dict", ttl=900) == {"a": 1}


class TestCacheTTLExpiry:
    """Test TTL expiry behavior."""

    def setup_method(self):
        cache.clear()

    def test_entry_expires_after_ttl(self):
        cache.put("expiring", "data")
        # Use a very short TTL to test expiry
        result = cache.get("expiring", ttl=0)
        # TTL=0 means anything older than 0 seconds is expired
        # Since time passes between put and get, this should be None
        # But time.time() resolution may return the same value
        # Use sleep to guarantee expiry
        time.sleep(0.05)
        result = cache.get("expiring", ttl=0)
        assert result is None

    def test_entry_valid_within_ttl(self):
        cache.put("fresh", "data")
        result = cache.get("fresh", ttl=60)
        assert result == "data"

    def test_ttl_boundary(self):
        """Entry should be accessible just within TTL."""
        cache.put("boundary", "data")
        # 10 second TTL, accessed immediately -- should succeed
        result = cache.get("boundary", ttl=10)
        assert result == "data"


class TestCacheInvalidation:
    """Test cache invalidation."""

    def setup_method(self):
        cache.clear()

    def test_invalidate_existing_key(self):
        cache.put("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1", ttl=900) is None

    def test_invalidate_nonexistent_key(self):
        # Should not raise
        cache.invalidate("nonexistent")

    def test_invalidate_does_not_affect_other_keys(self):
        cache.put("a", 1)
        cache.put("b", 2)
        cache.invalidate("a")
        assert cache.get("a", ttl=900) is None
        assert cache.get("b", ttl=900) == 2

    def test_clear_removes_all(self):
        cache.put("a", 1)
        cache.put("b", 2)
        cache.clear()
        assert cache.get("a", ttl=900) is None
        assert cache.get("b", ttl=900) is None


class TestCacheGetTimestamp:
    """Test get_timestamp method."""

    def setup_method(self):
        cache.clear()

    def test_returns_none_for_missing_key(self):
        assert cache.get_timestamp("missing") is None

    def test_returns_timestamp_after_put(self):
        before = time.time()
        cache.put("key1", "val")
        after = time.time()
        ts = cache.get_timestamp("key1")
        assert ts is not None
        assert before <= ts <= after


class TestCacheThreadSafety:
    """Basic concurrent access tests."""

    def setup_method(self):
        cache.clear()

    def test_concurrent_puts(self):
        """Multiple threads writing to the cache should not crash."""
        errors = []

        def writer(prefix, count):
            try:
                for i in range(count):
                    cache.put(f"{prefix}-{i}", i)
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(4):
            thread = threading.Thread(target=writer, args=(f"t{t}", 50))
            threads.append(thread)

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_reads_and_writes(self):
        """Concurrent reads and writes should not crash or corrupt data."""
        errors = []
        cache.put("shared", "initial")

        def reader(count):
            try:
                for _ in range(count):
                    cache.get("shared", ttl=900)
            except Exception as e:
                errors.append(e)

        def writer(count):
            try:
                for i in range(count):
                    cache.put("shared", f"value-{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader, args=(100,)),
            threading.Thread(target=reader, args=(100,)),
            threading.Thread(target=writer, args=(100,)),
            threading.Thread(target=writer, args=(100,)),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == [], f"Thread errors: {errors}"
        # The final value should be a string (not corrupted)
        result = cache.get("shared", ttl=900)
        assert isinstance(result, str)
