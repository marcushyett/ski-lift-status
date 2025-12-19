"""Serper.dev API client for web search."""

import os
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class SearchResult:
    """A single search result from Serper."""

    title: str
    url: str
    snippet: str
    position: int


@dataclass
class SerperResponse:
    """Response from Serper API."""

    query: str
    results: list[SearchResult]
    knowledge_graph: dict | None = None


class SerperClient:
    """Client for Serper.dev search API."""

    BASE_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str | None = None):
        """Initialize the Serper client.

        Args:
            api_key: Serper API key. If not provided, reads from SERPER_API_KEY or SERPER env var.
        """
        self.api_key = api_key or os.environ.get("SERPER_API_KEY") or os.environ.get("SERPER")
        if not self.api_key:
            raise ValueError(
                "Serper API key required. Set SERPER_API_KEY or SERPER environment variable "
                "or pass api_key parameter."
            )

    async def search(
        self,
        query: str,
        num_results: int = 10,
        country: str | None = None,
    ) -> SerperResponse:
        """Perform a web search.

        Args:
            query: The search query.
            num_results: Number of results to return.
            country: Country code for localized results (e.g., "us", "fr").

        Returns:
            SerperResponse with search results.
        """
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "q": query,
            "num": num_results,
        }

        if country:
            payload["gl"] = country

        logger.debug("serper_search", query=query, num_results=num_results)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.BASE_URL,
                headers=headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for i, item in enumerate(data.get("organic", [])):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    position=i + 1,
                )
            )

        logger.debug("serper_results", query=query, count=len(results))

        return SerperResponse(
            query=query,
            results=results,
            knowledge_graph=data.get("knowledgeGraph"),
        )

    async def search_lift_status_page(
        self,
        resort_name: str,
        lift_names: list[str],
        max_queries: int = 3,
    ) -> list[SerperResponse]:
        """Search for a resort's lift status page using lift names.

        Args:
            resort_name: Name of the ski resort.
            lift_names: List of lift names at the resort (for query refinement).
            max_queries: Maximum number of search queries to try.

        Returns:
            List of SerperResponse objects from different queries.
        """
        responses = []

        # Primary query: resort name + "lift status"
        query1 = f'{resort_name} lift status'
        responses.append(await self.search(query1))

        # Secondary query: with a specific lift name quoted
        if lift_names and len(responses) < max_queries:
            # Pick a distinctive lift name (longer names are often more unique)
            lift_name = max(lift_names[:5], key=len) if len(lift_names) >= 5 else lift_names[0]
            query2 = f'{resort_name} lift status "{lift_name}"'
            responses.append(await self.search(query2))

        # Tertiary query: "terrain status" variant
        if len(responses) < max_queries:
            query3 = f'{resort_name} terrain status lifts'
            responses.append(await self.search(query3))

        return responses
