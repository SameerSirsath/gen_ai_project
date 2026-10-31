"""
step1_web_scraper.py — Web scraping module.

Collects raw text from:
  • Company website (homepage + sub-pages)
  • Google / Bing search results
  • News articles
  • LinkedIn public company page (basic, no login required)
"""

import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from .config import (
    REQUEST_TIMEOUT, REQUEST_DELAY, MAX_PAGES_PER_SITE,
    USER_AGENT, SEARCH_QUERIES, SERPAPI_KEY
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_headers():
    return {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}


def _safe_get(url: str) -> requests.Response | None:
    """HTTP GET with error handling."""
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"    [WARN] Could not fetch {url}: {e}")
        return None


def _extract_text(html: str) -> str:
    """Strip HTML tags and return clean text."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove noisy elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse whitespace
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _same_domain(base_url: str, link: str) -> bool:
    base = urlparse(base_url).netloc
    target = urlparse(link).netloc
    return base == target or target == ""


# ─────────────────────────────────────────────
# 1. Company Website Crawler
# ─────────────────────────────────────────────

def scrape_company_website(company_name: str, base_url: str) -> list[dict]:
    """
    BFS crawl of a company website up to MAX_PAGES_PER_SITE pages.
    Returns list of {url, title, text} dicts.
    """
    print(f"\n[WEB] Crawling company website: {base_url}")
    visited, queue, results = set(), [base_url], []

    while queue and len(visited) < MAX_PAGES_PER_SITE:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        resp = _safe_get(url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title else url
        text = _extract_text(resp.text)

        results.append({
            "source": "company_website",
            "url": url,
            "title": title,
            "text": text,
            "company": company_name,
        })
        print(f"    ✓ Scraped: {title[:60]}")

        # Discover internal links
        for a_tag in soup.find_all("a", href=True):
            link = urljoin(url, a_tag["href"])
            if _same_domain(base_url, link) and link not in visited:
                queue.append(link)

        time.sleep(REQUEST_DELAY)

    return results


# ─────────────────────────────────────────────
# 2. Bing Search Scraper (no API key needed)
# ─────────────────────────────────────────────

def scrape_bing_search(company_name: str) -> list[dict]:
    """
    Runs pre-defined search queries on Bing and scrapes result pages.
    Returns list of {url, title, text, query} dicts.
    """
    print(f"\n[SEARCH] Running Bing searches for: {company_name}")
    all_results = []
    seen_urls = set()

    for query_template in SEARCH_QUERIES:
        query = query_template.format(company=company_name)
        search_url = f"https://www.bing.com/search?q={requests.utils.quote(query)}"

        resp = _safe_get(search_url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        result_cards = soup.select("li.b_algo")[:5]  # top 5 results per query

        for card in result_cards:
            a_tag = card.find("a")
            if not a_tag:
                continue
            result_url = a_tag.get("href", "")
            if not result_url.startswith("http") or result_url in seen_urls:
                continue
            seen_urls.add(result_url)

            # Skip PDF links here (handled separately)
            if result_url.lower().endswith(".pdf"):
                print(f"    [PDF] Found PDF link: {result_url}")
                all_results.append({
                    "source": "search_pdf_link",
                    "url": result_url,
                    "title": a_tag.get_text(strip=True),
                    "text": "",
                    "query": query,
                    "company": company_name,
                })
                continue

            # Scrape the actual page
            page_resp = _safe_get(result_url)
            if not page_resp:
                continue

            text = _extract_text(page_resp.text)
            title = BeautifulSoup(page_resp.text, "html.parser").title
            title = title.string.strip() if title else result_url

            all_results.append({
                "source": "search_result",
                "url": result_url,
                "title": title,
                "text": text[:5000],
                "query": query,
                "company": company_name,
            })
            print(f"    ✓ {title[:60]}")
            time.sleep(REQUEST_DELAY)

        time.sleep(REQUEST_DELAY)

    return all_results


# ─────────────────────────────────────────────
# 3. SerpAPI Search Scraper (Google Search & PDF Discovery)
# ─────────────────────────────────────────────

def scrape_serpapi_search(company_name: str) -> list[dict]:
    """
    Uses SerpAPI (Google Search) to discover:
      1. Direct PDF reports (annual report, 10-K, sustainability)
      2. Web overview, products, and news
    """
    print(f"\n[SEARCH] Running SerpAPI (Google Search) for: {company_name}")
    all_results = []
    seen_urls = set()

    # 1. Target PDF query first
    pdf_query = f"{company_name} annual report filetype:pdf"
    try:
        url = f"https://serpapi.com/search.json?q={requests.utils.quote(pdf_query)}&api_key={SERPAPI_KEY}&num=5"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("organic_results", []):
                link = item.get("link", "")
                if link and (link.lower().endswith(".pdf") or "pdf" in link.lower()):
                    if link not in seen_urls:
                        seen_urls.add(link)
                        title = item.get("title", f"{company_name} Report")
                        print(f"    [PDF] Found PDF via SerpAPI: {title[:50]} -> {link[:60]}")
                        all_results.append({
                            "source": "search_pdf_link",
                            "url": link,
                            "title": title,
                            "text": item.get("snippet", ""),
                            "query": pdf_query,
                            "company": company_name,
                        })
    except Exception as e:
        print(f"    [WARN] SerpAPI PDF search failed: {e}")

    # 2. Key information queries
    general_queries = [
        f"{company_name} company overview",
        f"{company_name} products services",
        f"{company_name} recent news financial results",
    ]

    for query in general_queries:
        try:
            url = f"https://serpapi.com/search.json?q={requests.utils.quote(query)}&api_key={SERPAPI_KEY}&num=4"
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for item in data.get("organic_results", [])[:3]:
                link = item.get("link", "")
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                title = item.get("title", link)
                snippet = item.get("snippet", "")

                # Fetch page text or fallback to snippet
                page_text = snippet
                page_resp = _safe_get(link)
                if page_resp and len(page_resp.text) > 200:
                    extracted = _extract_text(page_resp.text)
                    if len(extracted) > 100:
                        page_text = extracted[:4000]

                all_results.append({
                    "source": "search_result",
                    "url": link,
                    "title": title,
                    "text": page_text,
                    "query": query,
                    "company": company_name,
                })
                print(f"    ✓ {title[:60]}")
                time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"    [WARN] SerpAPI query '{query}' failed: {e}")

    return all_results


# ─────────────────────────────────────────────
# 4. LinkedIn Public Page Scraper (no login)
# ─────────────────────────────────────────────

def scrape_linkedin_public(company_name: str) -> list[dict]:
    """
    Scrapes the LinkedIn public company page (without login).
    NOTE: LinkedIn blocks most scrapers; this collects what's publicly visible.
    For full access, use LinkedIn API or a proxy service.
    """
    print(f"\n[LINKEDIN] Scraping LinkedIn public page for: {company_name}")
    slug = company_name.lower().replace(" ", "-").replace(",", "").replace(".", "")
    url = f"https://www.linkedin.com/company/{slug}/"

    resp = _safe_get(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract visible text sections
    sections = {}
    for tag in soup.find_all(["h1", "h2", "h3", "p", "span"]):
        text = tag.get_text(strip=True)
        if len(text) > 30:
            parent = tag.parent.name if tag.parent else "body"
            sections.setdefault(parent, []).append(text)

    combined = "\n".join([t for texts in sections.values() for t in texts])

    if not combined.strip():
        print("    [INFO] LinkedIn returned limited public content (login wall).")
        return []

    return [{
        "source": "linkedin",
        "url": url,
        "title": f"{company_name} - LinkedIn",
        "text": combined[:5000],
        "company": company_name,
    }]


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def collect_web_data(company_name: str, company_url: str = "") -> list[dict]:
    """
    Master function: collects web data from all sources.
    Args:
        company_name: e.g. "Tesla"
        company_url:  e.g. "https://www.tesla.com" (optional, auto-guessed if empty)
    Returns:
        List of raw data records.
    """
    if not company_url:
        slug = company_name.lower().replace(" ", "")
        company_url = f"https://www.{slug}.com"
        print(f"[INFO] No URL provided. Guessing: {company_url}")

    results = []
    # 1. Scrape official website
    results += scrape_company_website(company_name, company_url)

    # 2. Search engine scraping: SerpAPI if key configured, else Bing
    if SERPAPI_KEY:
        serp_results = scrape_serpapi_search(company_name)
        results += serp_results
        if not serp_results:
            print("    [INFO] SerpAPI returned no results, falling back to Bing search...")
            results += scrape_bing_search(company_name)
    else:
        results += scrape_bing_search(company_name)

    # 3. LinkedIn public page
    results += scrape_linkedin_public(company_name)

    print(f"\n[WEB] Total raw records collected: {len(results)}")
    return results
