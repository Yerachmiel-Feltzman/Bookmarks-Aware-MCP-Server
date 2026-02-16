"""Tests for metadata_store module."""
import pytest
import pytest_asyncio

from src.metadata_store import MetadataStore


@pytest_asyncio.fixture
async def store(metadata_db_path):
    """Create and initialize a test metadata store."""
    s = MetadataStore(metadata_db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.mark.asyncio
class TestMetadataStore:
    async def test_initialize_creates_db(self, metadata_db_path):
        store = MetadataStore(metadata_db_path)
        await store.initialize()
        assert metadata_db_path.exists()
        await store.close()

    async def test_upsert_and_get(self, store):
        await store.upsert_metadata(
            url="https://example.com",
            title="Example",
            summary="A test page.",
            tags=["test", "example"],
            content_hash="abc123",
        )
        meta = await store.get_metadata("https://example.com")
        assert meta is not None
        assert meta["title"] == "Example"
        assert meta["summary"] == "A test page."
        assert meta["tags"] == ["test", "example"]
        assert meta["content_hash"] == "abc123"

    async def test_get_nonexistent_returns_none(self, store):
        meta = await store.get_metadata("https://doesnotexist.com")
        assert meta is None

    async def test_upsert_updates_existing(self, store):
        await store.upsert_metadata(
            url="https://example.com",
            title="Original",
            summary="First version.",
            tags=["v1"],
        )
        await store.upsert_metadata(
            url="https://example.com",
            summary="Updated version.",
            tags=["v2"],
        )
        meta = await store.get_metadata("https://example.com")
        assert meta["summary"] == "Updated version."
        assert meta["tags"] == ["v2"]
        assert meta["title"] == "Original"  # preserved via COALESCE

    async def test_search_by_tags(self, store):
        await store.upsert_metadata(url="https://a.com", tags=["python", "tutorial"])
        await store.upsert_metadata(url="https://b.com", tags=["rust", "tutorial"])
        await store.upsert_metadata(url="https://c.com", tags=["python", "advanced"])

        results = await store.search_by_tags(["python"])
        urls = [r["url"] for r in results]
        assert "https://a.com" in urls
        assert "https://c.com" in urls
        assert "https://b.com" not in urls

    async def test_search_by_tags_any_match(self, store):
        await store.upsert_metadata(url="https://a.com", tags=["python"])
        await store.upsert_metadata(url="https://b.com", tags=["rust"])

        results = await store.search_by_tags(["python", "rust"])
        assert len(results) == 2

    async def test_get_all_metadata(self, store):
        await store.upsert_metadata(url="https://a.com", summary="A")
        await store.upsert_metadata(url="https://b.com", summary="B")

        all_meta = await store.get_all_metadata()
        assert len(all_meta) == 2

    async def test_delete_metadata(self, store):
        await store.upsert_metadata(url="https://example.com", summary="test")
        deleted = await store.delete_metadata("https://example.com")
        assert deleted is True
        meta = await store.get_metadata("https://example.com")
        assert meta is None

    async def test_delete_nonexistent_returns_false(self, store):
        deleted = await store.delete_metadata("https://doesnotexist.com")
        assert deleted is False

    async def test_tags_parsed_as_list(self, store):
        await store.upsert_metadata(url="https://example.com", tags=["a", "b", "c"])
        meta = await store.get_metadata("https://example.com")
        assert isinstance(meta["tags"], list)
        assert meta["tags"] == ["a", "b", "c"]

    async def test_empty_tags_returns_list(self, store):
        await store.upsert_metadata(url="https://example.com", summary="no tags")
        meta = await store.get_metadata("https://example.com")
        assert meta["tags"] == []
