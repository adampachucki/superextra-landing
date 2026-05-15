from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.tools.function_tool import FunctionTool

from superextra_agent import search_tools
from superextra_agent.search_tools import search_and_read_public_pages, search_web


def _response(payload, status_code=200, text="OK"):
    return SimpleNamespace(status_code=status_code, text=text, json=lambda: payload)


@pytest.fixture(autouse=True)
def reset_search_client():
    search_tools._client = None
    yield
    search_tools._client = None


@pytest.fixture(autouse=True)
def mock_cloud_log():
    with patch("superextra_agent.search_tools.emit_cloud_log") as mock:
        yield mock


def test_search_web_function_declaration_has_required_query():
    declaration = FunctionTool(search_web)._get_declaration()
    schema = declaration.parameters.model_dump(mode="json", exclude_none=True)

    assert declaration.name == "search_web"
    assert schema["required"] == ["query"]
    assert schema["properties"]["location"]["nullable"] is True
    assert schema["properties"]["freshness"]["nullable"] is True
    assert schema["properties"]["num_results"]["default"] == search_tools.MAX_RESULTS


def test_search_and_read_function_declaration_has_required_query():
    declaration = FunctionTool(search_and_read_public_pages)._get_declaration()
    schema = declaration.parameters.model_dump(mode="json", exclude_none=True)

    assert declaration.name == "search_and_read_public_pages"
    assert schema["required"] == ["query"]
    assert schema["properties"]["num_results"]["default"] == search_tools.MAX_RESULTS
    assert schema["properties"]["read_limit"]["default"] == search_tools.MAX_READ_LIMIT


@pytest.mark.asyncio
async def test_search_web_maps_params_and_normalizes_results(mock_cloud_log):
    first_page = [
        {
            "position": 1,
            "title": "Best pizza in Gdynia",
            "link": "https://example.com/pizza",
            "snippet": "A local guide to pizza.",
            "source": "Example",
            "date": "May 2026",
        },
        *[
            {
                "position": position,
                "title": f"No link result {position}",
                "snippet": "Skipped.",
            }
            for position in range(2, 11)
        ],
    ]
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            _response(
                {
                    "search_metadata": {"status": "Success"},
                    "organic_results": first_page,
                    "serpapi_pagination": {
                        "next_link": (
                            "https://serpapi.com/search.json?engine=google"
                            "&q=pizza+Gdynia&start=10&num=10"
                        )
                    },
                }
            ),
            _response(
                {
                    "search_metadata": {"status": "Success"},
                    "organic_results": [
                        {
                            "position": 11,
                            "title": "Best pasta in Gdynia",
                            "link": "https://example.com/pasta",
                            "snippet": "A local guide to pasta.",
                        }
                    ],
                }
            ),
        ]
    )
    tool_context = SimpleNamespace(session=SimpleNamespace(state={"runId": "run-search"}))

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client):
        result = await search_web(
            "pizza Gdynia",
            location="Gdynia, Poland",
            gl="PL",
            hl="pl",
            num_results=50,
            freshness="week",
            tool_context=tool_context,
        )

    assert result == {
        "status": "success",
        "query": "pizza Gdynia",
        "results": [
            {
                "title": "Best pizza in Gdynia",
                "url": "https://example.com/pizza",
                "domain": "example.com",
                "snippet": "A local guide to pizza.",
                "position": 1,
                "result_type": "organic",
                "source": "Example",
                "date": "May 2026",
            },
            {
                "title": "Best pasta in Gdynia",
                "url": "https://example.com/pasta",
                "domain": "example.com",
                "snippet": "A local guide to pasta.",
                "position": 2,
                "result_type": "organic",
            },
        ],
        "sources": [
            {
                "url": "https://example.com/pizza",
                "title": "Best pizza in Gdynia",
                "domain": "example.com",
            },
            {
                "url": "https://example.com/pasta",
                "title": "Best pasta in Gdynia",
                "domain": "example.com",
            },
        ],
        "result_count": 2,
    }
    assert mock_client.get.await_count == 2
    params = mock_client.get.await_args_list[0].kwargs["params"]
    assert params["engine"] == "google"
    assert params["q"] == "pizza Gdynia"
    assert params["location"] == "Gdynia, Poland"
    assert params["gl"] == "pl"
    assert params["hl"] == "pl"
    assert params["num"] == search_tools.SERPAPI_PAGE_SIZE
    assert "start" not in params
    assert params["tbs"] == "qdr:w"
    assert params["api_key"] == "test-key"
    second_params = mock_client.get.await_args_list[1].kwargs["params"]
    assert second_params["num"] == search_tools.SERPAPI_PAGE_SIZE
    assert second_params["start"] == search_tools.SERPAPI_PAGE_SIZE

    log = mock_cloud_log.call_args.kwargs
    assert log["run_id"] == "run-search"
    assert log["query"] == "pizza Gdynia"
    assert log["status"] == "success"
    assert log["result_count"] == 2
    assert log["source_count"] == 2
    assert log["params"]["num"] == search_tools.MAX_RESULTS
    assert "api_key" not in log["params"]


@pytest.mark.asyncio
async def test_search_web_uses_serpapi_next_link_for_next_offset():
    first_page = [
        {
            "position": position,
            "title": f"Result {position}",
            "link": f"https://example.com/{position}",
        }
        for position in range(1, 8)
    ]
    second_page = [
        {
            "position": position,
            "title": f"Result {position}",
            "link": f"https://example.com/{position}",
        }
        for position in range(8, 13)
    ]
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            _response(
                {
                    "search_metadata": {"status": "Success"},
                    "organic_results": first_page,
                    "serpapi_pagination": {
                        "next_link": (
                            "https://serpapi.com/search.json?engine=google"
                            "&q=odd+page&start=7&num=10"
                        )
                    },
                }
            ),
            _response(
                {
                    "search_metadata": {"status": "Success"},
                    "organic_results": second_page,
                }
            ),
        ]
    )

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client):
        result = await search_web("odd page", num_results=12)

    assert result["result_count"] == 12
    assert [item["url"] for item in result["results"]] == [
        *(f"https://example.com/{position}" for position in range(1, 13))
    ]
    assert mock_client.get.await_args_list[1].kwargs["params"]["start"] == 7
    assert mock_client.get.await_args_list[1].kwargs["params"]["num"] == 5


@pytest.mark.asyncio
async def test_search_web_handles_serpapi_error(mock_cloud_log):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_response(
            {
                "search_metadata": {"status": "Error"},
                "error": "Invalid API key",
            }
        )
    )

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client):
        result = await search_web("pizza")

    assert result == {"status": "error", "error_message": "Invalid API key"}
    assert mock_cloud_log.call_args.kwargs["error_reason"] == "api_error"


@pytest.mark.asyncio
async def test_search_web_empty_organic_results_is_success():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=_response({"search_metadata": {"status": "Success"}})
    )

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client):
        result = await search_web("very specific query")

    assert result["status"] == "success"
    assert result["results"] == []
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_search_web_invalid_freshness_returns_error_without_request():
    mock_client = AsyncMock()

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client):
        result = await search_web("pizza", freshness="recent")

    assert result["status"] == "error"
    assert "freshness" in result["error_message"]
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_search_and_read_reads_filtered_candidates(mock_cloud_log):
    search_response = _response(
        {
            "search_metadata": {"status": "Success"},
            "organic_results": [
                {
                    "position": 1,
                    "title": "Monsun listing",
                    "link": "https://www.trojmiasto.pl/Monsun-o96445.html#reviews",
                },
                {
                    "position": 2,
                    "title": "Monsun video",
                    "link": "https://www.tiktok.com/@food/video/1",
                },
                {
                    "position": 3,
                    "title": "Monsun forum",
                    "link": "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html",
                },
            ],
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=search_response)
    read_result = {
        "status": "success",
        "success_count": 2,
        "failed_count": 0,
        "results": [
            {
                "status": "success",
                "url": "https://www.trojmiasto.pl/Monsun-o96445.html",
                "content": "Title: Monsun Gdynia\n\nDetails",
            },
            {
                "status": "success",
                "url": "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html",
                "content": "Title: Forum\n\nDetails",
            },
        ],
        "sources": [
            {
                "url": "https://www.trojmiasto.pl/Monsun-o96445.html",
                "title": "Monsun Gdynia",
                "domain": "trojmiasto.pl",
                "provider": "fetched_page",
            },
            {
                "url": "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html",
                "title": "Forum",
                "domain": "m.trojmiasto.pl",
                "provider": "fetched_page",
            },
        ],
    }

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client), \
         patch("superextra_agent.search_tools.read_public_pages", AsyncMock(return_value=read_result)) as read:
        result = await search_and_read_public_pages("Monsun Gdynia", num_results=20, read_limit=10)

    assert result["status"] == "success"
    assert result["discovered_count"] == 3
    assert result["attempted_read_count"] == 2
    assert result["successful_read_count"] == 2
    assert result["failed_read_count"] == 0
    assert result["sources"] == read_result["sources"]
    assert [c["read_attempted"] for c in result["candidate_results"]] == [True, False, True]
    assert result["candidate_results"][1]["skip_reason"] == "social_or_app_page"
    read.assert_awaited_once_with([
        "https://www.trojmiasto.pl/Monsun-o96445.html",
        "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html",
    ])
    summary_log = mock_cloud_log.call_args_list[-1].kwargs
    assert summary_log["attempted_read_count"] == 2
    assert summary_log["successful_read_count"] == 2
    assert summary_log["source_count"] == 2


@pytest.mark.asyncio
async def test_search_and_read_dedupes_tracking_query_params():
    search_response = _response(
        {
            "search_metadata": {"status": "Success"},
            "organic_results": [
                {
                    "position": 1,
                    "title": "Monsun menu",
                    "link": "https://example.com/monsun?srsltid=one&utm_source=google",
                },
                {
                    "position": 2,
                    "title": "Monsun menu duplicate",
                    "link": "https://example.com/monsun?srsltid=two&utm_campaign=search",
                },
            ],
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=search_response)
    read_result = {
        "status": "success",
        "success_count": 1,
        "failed_count": 0,
        "results": [{"status": "success", "url": "https://example.com/monsun"}],
        "sources": [{"url": "https://example.com/monsun", "title": "Monsun menu"}],
    }

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client), \
         patch("superextra_agent.search_tools.read_public_pages", AsyncMock(return_value=read_result)) as read:
        result = await search_and_read_public_pages("Monsun Gdynia", read_limit=1)

    assert result["discovered_count"] == 1
    assert result["attempted_read_count"] == 1
    read.assert_awaited_once_with(["https://example.com/monsun"])


@pytest.mark.asyncio
async def test_search_and_read_errors_when_no_pages_read(mock_cloud_log):
    search_response = _response(
        {
            "search_metadata": {"status": "Success"},
            "organic_results": [
                {
                    "position": 1,
                    "title": "Monsun",
                    "link": "https://www.trojmiasto.pl/Monsun-o96445.html",
                }
            ],
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=search_response)
    read_result = {
        "status": "error",
        "success_count": 0,
        "failed_count": 1,
        "results": [{"status": "error", "url": "https://www.trojmiasto.pl/Monsun-o96445.html"}],
    }

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client), \
         patch("superextra_agent.search_tools.read_public_pages", AsyncMock(return_value=read_result)):
        result = await search_and_read_public_pages("Monsun Gdynia", num_results=10)

    assert result["status"] == "error"
    assert result["attempted_read_count"] == 1
    assert result["successful_read_count"] == 0
    assert result["failed_read_count"] == 1
    assert "failed to read" in result["error_message"]


@pytest.mark.asyncio
async def test_search_and_read_runs_supplemental_search_when_social_results_dominate():
    social_heavy = {
        "search_metadata": {"status": "Success"},
        "organic_results": [
            {
                "position": 1,
                "title": "Monsun listing",
                "link": "https://www.trojmiasto.pl/Monsun-o96445.html",
            },
            *[
                {
                    "position": position,
                    "title": f"Social result {position}",
                    "link": f"https://www.instagram.com/p/{position}/",
                }
                for position in range(2, 11)
            ],
        ],
    }
    supplement = {
        "search_metadata": {"status": "Success"},
        "organic_results": [
            {
                "position": 1,
                "title": "Forum",
                "link": "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html",
            },
            {
                "position": 2,
                "title": "Wanderlog",
                "link": "https://wanderlog.com/place/details/11587813/monsun-gdynia",
            },
        ],
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[_response(social_heavy), _response(supplement)])
    read_result = {
        "status": "success",
        "results": [
            {"status": "success", "url": "https://www.trojmiasto.pl/Monsun-o96445.html"},
            {"status": "success", "url": "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html"},
            {"status": "success", "url": "https://wanderlog.com/place/details/11587813/monsun-gdynia"},
        ],
        "sources": [
            {"url": "https://www.trojmiasto.pl/Monsun-o96445.html", "title": "Monsun"},
            {"url": "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html", "title": "Forum"},
            {"url": "https://wanderlog.com/place/details/11587813/monsun-gdynia", "title": "Wanderlog"},
        ],
    }

    with patch("superextra_agent.search_tools._get_client", return_value=mock_client), \
         patch("superextra_agent.search_tools.read_public_pages", AsyncMock(return_value=read_result)) as read:
        result = await search_and_read_public_pages("Monsun Gdynia", num_results=10)

    assert result["discovered_count"] == 12
    assert result["attempted_read_count"] == 3
    assert result["successful_read_count"] == 3
    assert len(result["search_queries"]) == 2
    assert "-site:instagram.com" in result["search_queries"][1]
    read.assert_awaited_once_with([
        "https://www.trojmiasto.pl/Monsun-o96445.html",
        "https://m.trojmiasto.pl/forum/Monsun-c2,96445.html",
        "https://wanderlog.com/place/details/11587813/monsun-gdynia",
    ])
