"""Tests for enrich_all tool and add_bookmark auto-fetch enrichment."""
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from src.server import enrich_all_tool, add_bookmark_tool
from src.metadata_store import MetadataStore


@pytest_asyncio.fixture
async def metadata_store(tmp_path):
    """Create a temporary metadata store."""
    store = MetadataStore(db_path=tmp_path / "test_meta.db")
    await store.initialize()
    yield store
    await store.close()


class TestEnrichAll:
    @pytest.mark.asyncio
    async def test_no_bookmarks_returns_empty(self):
        """enrich_all with no bookmarks returns appropriate message."""
        with patch("src.server.load_bookmarks", return_value=[]):
            result = await enrich_all_tool(batch_size=5)
            assert result[0].text == "No bookmarks found."

    @pytest.mark.asyncio
    async def test_all_enriched_returns_status(self, metadata_store):
        """enrich_all when all bookmarks are enriched reports completion."""
        bookmarks = [
            {"url": "https://example.com", "title": "Example"},
        ]
        await metadata_store.upsert_metadata(
            url="https://example.com", summary="A test", tags=["test"]
        )

        with patch("src.server.load_bookmarks", return_value=bookmarks), \
             patch("src.server.get_metadata_store", return_value=metadata_store):
            result = await enrich_all_tool(batch_size=5)
            data = json.loads(result[0].text)
            assert data["status"] == "all_enriched"
            assert data["total_bookmarks"] == 1

    @pytest.mark.asyncio
    async def test_fetches_unenriched_batch(self, metadata_store):
        """enrich_all fetches content for unenriched bookmarks."""
        bookmarks = [
            {"url": "https://a.com", "title": "A"},
            {"url": "https://b.com", "title": "B"},
            {"url": "https://c.com", "title": "C"},
        ]

        async def mock_fetch(url):
            return f"Content of {url}"

        with patch("src.server.load_bookmarks", return_value=bookmarks), \
             patch("src.server.get_metadata_store", return_value=metadata_store), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await enrich_all_tool(batch_size=2)
            data = json.loads(result[0].text)

            assert data["fetched"] == 2
            assert data["remaining_unenriched"] == 1
            assert len(data["batch_results"]) == 2
            assert data["batch_results"][0]["status"] == "fetched"
            assert "content" in data["batch_results"][0]
            assert "content_hash" in data["batch_results"][0]

    @pytest.mark.asyncio
    async def test_handles_fetch_failures(self, metadata_store):
        """enrich_all handles fetch failures gracefully."""
        bookmarks = [
            {"url": "https://private.com", "title": "Private"},
        ]

        async def mock_fetch(url):
            return None  # Simulates failed fetch

        with patch("src.server.load_bookmarks", return_value=bookmarks), \
             patch("src.server.get_metadata_store", return_value=metadata_store), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await enrich_all_tool(batch_size=5)
            data = json.loads(result[0].text)

            assert data["fetched"] == 0
            assert data["failed"] == 1
            assert data["batch_results"][0]["status"] == "fetch_failed"

    @pytest.mark.asyncio
    async def test_batch_size_limits_results(self, metadata_store):
        """enrich_all respects batch_size parameter."""
        bookmarks = [{"url": f"https://{i}.com", "title": f"Site {i}"} for i in range(10)]

        async def mock_fetch(url):
            return f"Content of {url}"

        with patch("src.server.load_bookmarks", return_value=bookmarks), \
             patch("src.server.get_metadata_store", return_value=metadata_store), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await enrich_all_tool(batch_size=3)
            data = json.loads(result[0].text)

            assert len(data["batch_results"]) == 3
            assert data["remaining_unenriched"] == 7

    @pytest.mark.asyncio
    async def test_instruction_includes_next_batch_hint(self, metadata_store):
        """enrich_all instruction tells agent to call again when remaining > 0."""
        bookmarks = [
            {"url": "https://a.com", "title": "A"},
            {"url": "https://b.com", "title": "B"},
        ]

        async def mock_fetch(url):
            return "content"

        with patch("src.server.load_bookmarks", return_value=bookmarks), \
             patch("src.server.get_metadata_store", return_value=metadata_store), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await enrich_all_tool(batch_size=1)
            data = json.loads(result[0].text)

            assert "call enrich_all again" in data["instruction"]
            assert "1 remaining" in data["instruction"]

    @pytest.mark.asyncio
    async def test_last_batch_instruction(self, metadata_store):
        """enrich_all instruction says 'last batch' when remaining == 0."""
        bookmarks = [{"url": "https://a.com", "title": "A"}]

        async def mock_fetch(url):
            return "content"

        with patch("src.server.load_bookmarks", return_value=bookmarks), \
             patch("src.server.get_metadata_store", return_value=metadata_store), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await enrich_all_tool(batch_size=5)
            data = json.loads(result[0].text)

            assert "last batch" in data["instruction"]


class TestAddBookmarkAutoFetch:
    @pytest.mark.asyncio
    async def test_auto_fetches_content_on_add(self, tmp_path):
        """add_bookmark auto-fetches page content after successful add."""
        async def mock_fetch(url):
            return "Page content for testing"

        mock_tracker = AsyncMock()
        mock_tracker.record_change = AsyncMock()

        with patch("src.server._get_bookmarks_path", return_value=tmp_path / "Bookmarks"), \
             patch("src.server.add_bookmark", return_value=True), \
             patch("src.server.invalidate_bookmarks_cache"), \
             patch("src.server.get_change_tracker", return_value=mock_tracker), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await add_bookmark_tool("https://example.com", "Example", "bookmark_bar")
            data = json.loads(result[0].text)

            assert data["status"] == "added"
            assert data["page_content"] == "Page content for testing"
            assert "content_hash" in data
            assert "MUST" in data["enrichment_hint"]

    @pytest.mark.asyncio
    async def test_handles_fetch_failure_gracefully(self, tmp_path):
        """add_bookmark still succeeds even if auto-fetch fails."""
        async def mock_fetch(url):
            return None

        mock_tracker = AsyncMock()
        mock_tracker.record_change = AsyncMock()

        with patch("src.server._get_bookmarks_path", return_value=tmp_path / "Bookmarks"), \
             patch("src.server.add_bookmark", return_value=True), \
             patch("src.server.invalidate_bookmarks_cache"), \
             patch("src.server.get_change_tracker", return_value=mock_tracker), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await add_bookmark_tool("https://private.com", "Private", "bookmark_bar")
            data = json.loads(result[0].text)

            assert data["status"] == "added"
            assert "page_content" not in data
            assert "authentication" in data["enrichment_hint"].lower()

    @pytest.mark.asyncio
    async def test_handles_fetch_exception_gracefully(self, tmp_path):
        """add_bookmark still succeeds even if auto-fetch throws."""
        async def mock_fetch(url):
            raise Exception("Network error")

        mock_tracker = AsyncMock()
        mock_tracker.record_change = AsyncMock()

        with patch("src.server._get_bookmarks_path", return_value=tmp_path / "Bookmarks"), \
             patch("src.server.add_bookmark", return_value=True), \
             patch("src.server.invalidate_bookmarks_cache"), \
             patch("src.server.get_change_tracker", return_value=mock_tracker), \
             patch("src.server.fetch_page_content", side_effect=mock_fetch):
            result = await add_bookmark_tool("https://error.com", "Error", "bookmark_bar")
            data = json.loads(result[0].text)

            assert data["status"] == "added"
            assert "auto-fetch failed" in data["enrichment_hint"].lower()
