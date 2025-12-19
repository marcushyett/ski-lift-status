"""LangGraph-based agent for discovering resort lift status pages."""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

import httpx
import structlog
from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI

from ...models import Lift
from .serper import SerperClient, SearchResult

logger = structlog.get_logger()


class DiscoveryAction(str, Enum):
    """Actions the discovery agent can take."""

    SEARCH = "search"
    ANALYZE_RESULTS = "analyze_results"
    VALIDATE_PAGE = "validate_page"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class DiscoveryResult:
    """Result of status page discovery."""

    resort_id: str
    resort_name: str
    success: bool
    status_page_url: str | None = None
    website_url: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    search_queries: list[str] = field(default_factory=list)
    candidate_urls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DiscoveryState(TypedDict):
    """State for the discovery agent."""

    # Input
    resort_id: str
    resort_name: str
    resort_website: str | None
    lift_names: list[str]

    # Search state
    search_results: list[dict]
    search_queries: list[str]
    candidate_urls: list[tuple[str, float, str]]  # (url, score, reason)

    # Validation state
    validated_url: str | None
    validation_confidence: float
    validation_reasoning: str

    # Agent state
    action: DiscoveryAction
    attempt: int
    max_attempts: int
    errors: list[str]
    is_complete: bool


# Status page URL patterns that are likely to be correct
STATUS_PAGE_PATTERNS = [
    r"/lift[s]?[-_/]?status",
    r"/terrain[-_/]?status",
    r"/conditions",
    r"/snow[-_]?report",
    r"/mountain[-_/]?conditions",
    r"/pist[ae]s?[-_]?e?[-_]?remontee",  # French
    r"/ouverture",  # French
    r"/live[-_]?info",
    r"/impianti",  # Italian
    r"/anlagen",  # German
    r"/lifte",  # German
]

# Domains that are unlikely to be official resort pages
EXCLUDED_DOMAINS = [
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "youtube.com",
    "tripadvisor.com",
    "yelp.com",
    "wikipedia.org",
    "wikidata.org",
    "onthesnow.com",
    "snowforecast.com",
    "snow-forecast.com",
    "j2ski.com",
    "skiinfo.com",
    "skiresort.info",
]


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    match = re.search(r"https?://([^/]+)", url)
    return match.group(1) if match else ""


def _score_url(url: str, resort_name: str, title: str, snippet: str) -> tuple[float, str]:
    """Score a URL for likelihood of being a status page.

    Returns (score, reasoning).
    """
    score = 0.0
    reasons = []

    domain = _extract_domain(url)
    url_lower = url.lower()

    # Check for excluded domains
    for excluded in EXCLUDED_DOMAINS:
        if excluded in domain:
            return 0.0, f"Excluded domain: {excluded}"

    # Check URL patterns
    for pattern in STATUS_PAGE_PATTERNS:
        if re.search(pattern, url_lower):
            score += 0.3
            reasons.append(f"URL matches status page pattern: {pattern}")
            break

    # Check if domain contains resort name words
    resort_words = resort_name.lower().split()
    domain_lower = domain.lower()
    for word in resort_words:
        if len(word) > 3 and word in domain_lower:
            score += 0.2
            reasons.append(f"Domain contains resort name word: {word}")
            break

    # Check title for relevant keywords
    title_lower = title.lower()
    status_keywords = ["lift", "status", "terrain", "conditions", "open", "closed", "pistes", "remontees"]
    for keyword in status_keywords:
        if keyword in title_lower:
            score += 0.1
            reasons.append(f"Title contains keyword: {keyword}")
            break

    # Check snippet for lift-related content
    snippet_lower = snippet.lower()
    if any(kw in snippet_lower for kw in ["lift", "chairlift", "gondola", "open", "closed", "status"]):
        score += 0.15
        reasons.append("Snippet contains lift-related content")

    # Prefer HTTPS
    if url.startswith("https://"):
        score += 0.05
        reasons.append("Uses HTTPS")

    # Bonus for being a dedicated status page URL (not just homepage)
    if len(url.replace("https://", "").replace("http://", "").split("/")) > 2:
        score += 0.1
        reasons.append("Dedicated page (not homepage)")

    return min(score, 1.0), "; ".join(reasons) if reasons else "No strong signals"


async def search_node(state: DiscoveryState) -> DiscoveryState:
    """Perform web search for status pages."""
    try:
        client = SerperClient()
        responses = await client.search_lift_status_page(
            resort_name=state["resort_name"],
            lift_names=state["lift_names"],
        )

        all_results = []
        queries = []
        for response in responses:
            queries.append(response.query)
            for result in response.results:
                all_results.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "position": result.position,
                    "query": response.query,
                })

        return {
            **state,
            "search_results": all_results,
            "search_queries": queries,
            "action": DiscoveryAction.ANALYZE_RESULTS,
        }
    except Exception as e:
        logger.error("search_failed", error=str(e), resort=state["resort_name"])
        return {
            **state,
            "errors": state["errors"] + [f"Search failed: {e}"],
            "action": DiscoveryAction.FAIL,
        }


async def analyze_results_node(state: DiscoveryState) -> DiscoveryState:
    """Analyze search results using LLM to find best candidates."""
    results = state["search_results"]
    if not results:
        return {
            **state,
            "errors": state["errors"] + ["No search results found"],
            "action": DiscoveryAction.FAIL,
        }

    # First pass: score all URLs heuristically
    candidates = []
    seen_urls = set()

    for result in results:
        url = result["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        score, reason = _score_url(
            url=url,
            resort_name=state["resort_name"],
            title=result["title"],
            snippet=result["snippet"],
        )

        if score > 0:
            candidates.append((url, score, reason))

    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Take top candidates for LLM analysis
    top_candidates = candidates[:10]

    if not top_candidates:
        return {
            **state,
            "errors": state["errors"] + ["No viable candidates found in search results"],
            "action": DiscoveryAction.FAIL,
        }

    # Use LLM to pick the best URL
    try:
        openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Build context for LLM
        candidate_info = "\n".join([
            f"{i+1}. URL: {url}\n   Score: {score:.2f}\n   Reason: {reason}"
            for i, (url, score, reason) in enumerate(top_candidates)
        ])

        lift_examples = ", ".join(state["lift_names"][:5]) if state["lift_names"] else "Unknown"

        prompt = f"""You are helping find the official lift status page for a ski resort.

Resort: {state["resort_name"]}
Official website (if known): {state["resort_website"] or "Unknown"}
Example lift names at this resort: {lift_examples}

Here are the candidate URLs found from web search, with heuristic scores:

{candidate_info}

Your task:
1. Identify which URL is most likely the official lift/terrain status page for this resort
2. The page should show real-time lift and run status (open/closed)
3. Prefer official resort domains over aggregator sites
4. Prefer dedicated status pages over general homepages

Respond with ONLY a JSON object:
{{
    "selected_url": "the best URL or null if none suitable",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of your choice"
}}"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content
        import json
        llm_result = json.loads(result_text)

        selected_url = llm_result.get("selected_url")
        confidence = llm_result.get("confidence", 0.0)
        reasoning = llm_result.get("reasoning", "")

        if selected_url and confidence >= 0.5:
            return {
                **state,
                "candidate_urls": top_candidates,
                "validated_url": selected_url,
                "validation_confidence": confidence,
                "validation_reasoning": reasoning,
                "action": DiscoveryAction.VALIDATE_PAGE,
            }
        else:
            # Try the highest scoring candidate anyway
            best_url, best_score, _ = top_candidates[0]
            return {
                **state,
                "candidate_urls": top_candidates,
                "validated_url": best_url,
                "validation_confidence": best_score,
                "validation_reasoning": f"LLM unsure (confidence={confidence}), using highest heuristic score",
                "action": DiscoveryAction.VALIDATE_PAGE,
            }

    except Exception as e:
        logger.warning("llm_analysis_failed", error=str(e))
        # Fallback to heuristic scoring
        best_url, best_score, best_reason = top_candidates[0]
        return {
            **state,
            "candidate_urls": top_candidates,
            "validated_url": best_url,
            "validation_confidence": best_score,
            "validation_reasoning": f"Heuristic selection (LLM failed): {best_reason}",
            "action": DiscoveryAction.VALIDATE_PAGE,
        }


async def validate_page_node(state: DiscoveryState) -> DiscoveryState:
    """Validate the selected page is actually accessible."""
    url = state["validated_url"]
    if not url:
        return {
            **state,
            "action": DiscoveryAction.FAIL,
            "errors": state["errors"] + ["No URL to validate"],
        }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SkiLiftStatus/1.0)"
            })
            response.raise_for_status()

            # Check if the page contains lift-related content
            content = response.text.lower()
            lift_indicators = ["lift", "chairlift", "gondola", "terrain", "piste", "slope", "remontee"]

            if any(indicator in content for indicator in lift_indicators):
                logger.info(
                    "page_validated",
                    url=url,
                    confidence=state["validation_confidence"],
                )
                return {
                    **state,
                    "action": DiscoveryAction.COMPLETE,
                    "is_complete": True,
                }
            else:
                # Page accessible but may not be the right one
                logger.warning("page_no_lift_content", url=url)
                return {
                    **state,
                    "validation_confidence": state["validation_confidence"] * 0.5,
                    "validation_reasoning": state["validation_reasoning"] + " (no lift keywords found)",
                    "action": DiscoveryAction.COMPLETE,  # Still complete, but lower confidence
                    "is_complete": True,
                }

    except Exception as e:
        logger.warning("page_validation_failed", url=url, error=str(e))

        # Try next candidate if available
        attempt = state["attempt"] + 1
        if attempt < state["max_attempts"] and len(state["candidate_urls"]) > attempt:
            next_url, next_score, next_reason = state["candidate_urls"][attempt]
            return {
                **state,
                "validated_url": next_url,
                "validation_confidence": next_score,
                "validation_reasoning": f"Fallback candidate: {next_reason}",
                "attempt": attempt,
                "action": DiscoveryAction.VALIDATE_PAGE,
            }

        return {
            **state,
            "errors": state["errors"] + [f"Page validation failed: {e}"],
            "action": DiscoveryAction.FAIL,
        }


def complete_node(state: DiscoveryState) -> DiscoveryState:
    """Mark discovery as complete."""
    return {
        **state,
        "is_complete": True,
    }


def fail_node(state: DiscoveryState) -> DiscoveryState:
    """Mark discovery as failed."""
    return {
        **state,
        "is_complete": True,
        "validated_url": None,
        "validation_confidence": 0.0,
    }


def route_action(state: DiscoveryState) -> str:
    """Route to next node based on action."""
    action = state["action"]

    if action == DiscoveryAction.SEARCH:
        return "search"
    elif action == DiscoveryAction.ANALYZE_RESULTS:
        return "analyze_results"
    elif action == DiscoveryAction.VALIDATE_PAGE:
        return "validate_page"
    elif action == DiscoveryAction.COMPLETE:
        return "complete"
    elif action == DiscoveryAction.FAIL:
        return "fail"
    else:
        return END


def build_discovery_graph() -> StateGraph:
    """Build the LangGraph for status page discovery."""
    graph = StateGraph(DiscoveryState)

    # Add nodes
    graph.add_node("search", search_node)
    graph.add_node("analyze_results", analyze_results_node)
    graph.add_node("validate_page", validate_page_node)
    graph.add_node("complete", complete_node)
    graph.add_node("fail", fail_node)

    # Add edges
    graph.add_edge("search", "analyze_results")
    graph.add_conditional_edges(
        "analyze_results",
        lambda s: s["action"].value,
        {
            DiscoveryAction.VALIDATE_PAGE.value: "validate_page",
            DiscoveryAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "validate_page",
        lambda s: s["action"].value,
        {
            DiscoveryAction.COMPLETE.value: "complete",
            DiscoveryAction.FAIL.value: "fail",
            DiscoveryAction.VALIDATE_PAGE.value: "validate_page",  # retry with next candidate
        },
    )
    graph.add_edge("complete", END)
    graph.add_edge("fail", END)

    # Set entry point
    graph.set_entry_point("search")

    return graph


class DiscoveryAgent:
    """Agent for discovering resort lift status pages."""

    def __init__(self, max_attempts: int = 3):
        """Initialize the discovery agent.

        Args:
            max_attempts: Maximum validation attempts per resort.
        """
        self.max_attempts = max_attempts
        self.graph = build_discovery_graph()
        self.app = self.graph.compile()

    async def discover(
        self,
        resort_id: str,
        resort_name: str,
        lift_names: list[str],
        resort_website: str | None = None,
    ) -> DiscoveryResult:
        """Discover the lift status page for a resort.

        Args:
            resort_id: OpenSkiMap resort ID.
            resort_name: Name of the resort.
            lift_names: List of lift names at the resort.
            resort_website: Official resort website (if known).

        Returns:
            DiscoveryResult with discovered URL and metadata.
        """
        initial_state: DiscoveryState = {
            "resort_id": resort_id,
            "resort_name": resort_name,
            "resort_website": resort_website,
            "lift_names": lift_names,
            "search_results": [],
            "search_queries": [],
            "candidate_urls": [],
            "validated_url": None,
            "validation_confidence": 0.0,
            "validation_reasoning": "",
            "action": DiscoveryAction.SEARCH,
            "attempt": 0,
            "max_attempts": self.max_attempts,
            "errors": [],
            "is_complete": False,
        }

        # Run the graph
        final_state = await self.app.ainvoke(initial_state)

        # Extract website URL from validated URL
        website_url = None
        if final_state["validated_url"]:
            domain = _extract_domain(final_state["validated_url"])
            if domain:
                website_url = f"https://{domain}"

        return DiscoveryResult(
            resort_id=resort_id,
            resort_name=resort_name,
            success=final_state["validated_url"] is not None,
            status_page_url=final_state["validated_url"],
            website_url=resort_website or website_url,
            confidence=final_state["validation_confidence"],
            reasoning=final_state["validation_reasoning"],
            search_queries=final_state["search_queries"],
            candidate_urls=[url for url, _, _ in final_state["candidate_urls"]],
            errors=final_state["errors"],
        )


async def run_discovery_for_resort(
    resort_id: str,
    resort_name: str,
    lifts: list[Lift],
    resort_website: str | None = None,
) -> DiscoveryResult:
    """Run discovery for a single resort.

    Args:
        resort_id: OpenSkiMap resort ID.
        resort_name: Name of the resort.
        lifts: List of lifts at the resort.
        resort_website: Official resort website (if known).

    Returns:
        DiscoveryResult with discovered status page.
    """
    agent = DiscoveryAgent()

    # Extract lift names
    lift_names = [lift.name for lift in lifts if lift.name]

    return await agent.discover(
        resort_id=resort_id,
        resort_name=resort_name,
        lift_names=lift_names,
        resort_website=resort_website,
    )


async def run_discovery_for_resorts(
    resorts: list[tuple[str, str, list[Lift], str | None]],
) -> list[DiscoveryResult]:
    """Run discovery for multiple resorts.

    Args:
        resorts: List of (resort_id, resort_name, lifts, website) tuples.

    Returns:
        List of DiscoveryResult objects.
    """
    import asyncio

    agent = DiscoveryAgent()
    results = []

    for resort_id, resort_name, lifts, website in resorts:
        lift_names = [lift.name for lift in lifts if lift.name]

        logger.info("discovering_resort", resort_name=resort_name, lift_count=len(lift_names))

        result = await agent.discover(
            resort_id=resort_id,
            resort_name=resort_name,
            lift_names=lift_names,
            resort_website=website,
        )
        results.append(result)

        # Small delay to avoid rate limiting
        await asyncio.sleep(1.0)

    return results
