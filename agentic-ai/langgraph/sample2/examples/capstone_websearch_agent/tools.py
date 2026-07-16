"""Real, key-free web search + scrape -- the modern replacement for
graph_websearch_agent's tools/google_serper.py (needs a paid Serper API key)
and tools/basic_scraper.py. DuckDuckGo's HTML endpoint needs no API key at
all, which keeps this capstone runnable by anyone who copies .env.example
and only fills in an OpenAI key.
"""

import requests
from bs4 import BeautifulSoup


def search_web(query: str, max_results: int = 5) -> str:
    response = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    lines = []
    for result in soup.select(".result")[:max_results]:
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href", "")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        lines.append(f"Title: {title}\nLink: {link}\nSnippet: {snippet}\n---")

    return "\n".join(lines) if lines else "No results found."


def scrape_url(url: str, max_chars: int = 3000) -> str:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    text = " ".join(soup.stripped_strings)
    return text[:max_chars]
