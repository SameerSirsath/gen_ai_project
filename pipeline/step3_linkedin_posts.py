"""
step3_linkedin_posts.py — LinkedIn Posts & Social Intelligence Module.

Strategies (in order of availability):
  1. LinkedIn Official API (if you have access)
  2. Public profile scraping via HTTP (no login, limited)
  3. Third-party LinkedIn data providers (RapidAPI / ProxyCurl)

The module returns structured post data: text, date, likes, comments, topics.
"""

import time
import re
import requests
from bs4 import BeautifulSoup

from .config import (
    REQUEST_TIMEOUT, REQUEST_DELAY, USER_AGENT,
    LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
    SERPAPI_KEY, PROXYCURL_API_KEY
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_headers(extra: dict = None) -> dict:
    h = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if extra:
        h.update(extra)
    return h


def _clean_linkedin_text(text: str) -> str:
    """Remove excessive whitespace and LinkedIn UI noise."""
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 10]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Strategy 1: ProxyCurl / RapidAPI (paid but reliable)
# ─────────────────────────────────────────────

def fetch_via_proxycurl(company_name: str, linkedin_url: str, api_key: str) -> list[dict]:
    """
    Uses ProxyCurl API to fetch LinkedIn company posts.
    Sign up: https://nubela.co/proxycurl
    """
    print(f"\n[LINKEDIN] Fetching via ProxyCurl API...")
    endpoint = "https://nubela.co/proxycurl/api/linkedin/company/posts"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"linkedin_company_profile_url": linkedin_url, "type": "posts"}

    try:
        resp = requests.get(endpoint, headers=headers, params=params,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("posts", [])

        results = []
        for post in posts:
            results.append({
                "source": "linkedin_post_proxycurl",
                "url": linkedin_url,
                "title": f"LinkedIn Post – {company_name}",
                "text": post.get("text", ""),
                "date": post.get("posted_at", ""),
                "likes": post.get("num_likes", 0),
                "comments": post.get("num_comments", 0),
                "company": company_name,
            })
        print(f"    ✓ Retrieved {len(results)} posts via ProxyCurl")
        return results
    except Exception as e:
        print(f"    [WARN] ProxyCurl failed: {e}")
        return []


# ─────────────────────────────────────────────
# Strategy 2: Public Scrape (no login, what's visible)
# ─────────────────────────────────────────────

def fetch_linkedin_public_posts(company_name: str) -> list[dict]:
    """
    Scrapes publicly visible content from LinkedIn company page.
    NOTE: LinkedIn heavily restricts scraping. This collects what's accessible
    without login — typically just the company description and basic info.
    For full post data, use ProxyCurl or LinkedIn API.
    """
    print(f"\n[LINKEDIN] Scraping public LinkedIn posts for: {company_name}")
    slug = company_name.lower().replace(" ", "-").replace(",", "").replace(".", "")
    urls_to_try = [
        f"https://www.linkedin.com/company/{slug}/posts/",
        f"https://www.linkedin.com/company/{slug}/",
        f"https://www.linkedin.com/company/{slug}/about/",
    ]

    results = []
    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # Try to extract post-like content
                post_candidates = soup.find_all(
                    "div", class_=re.compile(r"(feed-shared|update|post|content)", re.I)
                )

                if post_candidates:
                    for div in post_candidates[:10]:
                        text = _clean_linkedin_text(div.get_text())
                        if len(text) > 50:
                            results.append({
                                "source": "linkedin_post_public",
                                "url": url,
                                "title": f"LinkedIn Post – {company_name}",
                                "text": text[:2000],
                                "date": "",
                                "likes": 0,
                                "comments": 0,
                                "company": company_name,
                            })
                else:
                    # Fall back: grab any meaningful paragraph
                    for p in soup.find_all("p"):
                        text = p.get_text(strip=True)
                        if len(text) > 80:
                            results.append({
                                "source": "linkedin_about",
                                "url": url,
                                "title": f"LinkedIn About – {company_name}",
                                "text": text,
                                "company": company_name,
                            })

            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"    [WARN] Failed {url}: {e}")

    if not results:
        print("    [INFO] LinkedIn requires login for post data. "
              "Set PROXYCURL_API_KEY env variable for full access.")

    print(f"    ✓ LinkedIn: {len(results)} records collected")
    return results


# ─────────────────────────────────────────────
# Strategy 3: Search-based LinkedIn Discovery via SerpAPI
# ─────────────────────────────────────────────

def fetch_linkedin_via_serpapi(company_name: str) -> list[dict]:
    """
    Uses SerpAPI (Google Search) to discover real LinkedIn posts and company updates.
    """
    if not SERPAPI_KEY:
        return []

    print(f"\n[LINKEDIN] Searching LinkedIn posts via SerpAPI for: {company_name}")
    results = []
    queries = [
        f'site:linkedin.com/posts "{company_name}"',
        f'site:linkedin.com/company "{company_name}"',
    ]

    for query in queries:
        url = f"https://serpapi.com/search.json?q={requests.utils.quote(query)}&api_key={SERPAPI_KEY}&num=5"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("organic_results", [])[:4]:
                    snippet = item.get("snippet", "")
                    title = item.get("title", f"LinkedIn – {company_name}")
                    link = item.get("link", "")
                    if snippet and len(snippet) > 30:
                        results.append({
                            "source": "linkedin_search_snippet",
                            "url": link,
                            "title": title,
                            "text": snippet,
                            "company": company_name,
                        })
                        print(f"    ✓ {title[:60]}")
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"    [WARN] SerpAPI LinkedIn query failed: {e}")

    return results


# ─────────────────────────────────────────────
# Strategy 4: Search-based LinkedIn Post Discovery (Bing Fallback)
# ─────────────────────────────────────────────

def fetch_linkedin_via_google(company_name: str) -> list[dict]:
    """
    Searches Google/Bing for cached LinkedIn posts about the company.
    Useful when direct LinkedIn access is blocked.
    """
    print(f"\n[LINKEDIN] Searching for LinkedIn content via Bing...")
    results = []
    queries = [
        f'site:linkedin.com/posts "{company_name}"',
        f'site:linkedin.com "{company_name}" company update',
    ]

    for query in queries:
        search_url = f"https://www.bing.com/search?q={requests.utils.quote(query)}"
        try:
            resp = requests.get(search_url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for li in soup.select("li.b_algo")[:5]:
                    snippet = li.find("p")
                    a_tag = li.find("a")
                    if snippet and a_tag:
                        text = snippet.get_text(strip=True)
                        url = a_tag.get("href", "")
                        if len(text) > 40:
                            results.append({
                                "source": "linkedin_search_snippet",
                                "url": url,
                                "title": f"LinkedIn Post Snippet – {company_name}",
                                "text": text,
                                "company": company_name,
                            })
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"    [WARN] Search error: {e}")

    print(f"    ✓ Found {len(results)} LinkedIn snippets via search")
    return results


# ─────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────

def collect_linkedin_data(
    company_name: str,
    proxycurl_api_key: str = "",
    company_linkedin_url: str = "",
) -> list[dict]:
    """
    Master function: collects LinkedIn data using best available method.
    Args:
        company_name:         Target company name
        proxycurl_api_key:    Optional ProxyCurl API key for full post access
        company_linkedin_url: Full LinkedIn company URL (optional)
    Returns:
        List of LinkedIn data records
    """
    results = []
    pk = proxycurl_api_key or PROXYCURL_API_KEY
    if not company_linkedin_url:
        slug = company_name.lower().replace(" ", "-").replace(",", "").replace(".", "")
        company_linkedin_url = f"https://www.linkedin.com/company/{slug}"

    # Method 1: SerpAPI (Google indexed LinkedIn posts & updates)
    if SERPAPI_KEY:
        serp_posts = fetch_linkedin_via_serpapi(company_name)
        results.extend(serp_posts)

    # Method 2: ProxyCurl (if key configured and not sunset)
    if pk and not results:
        results.extend(fetch_via_proxycurl(company_name, company_linkedin_url, pk))

    # Method 3: Public scrape
    if not results:
        results.extend(fetch_linkedin_public_posts(company_name))

    # Method 4: Search-based discovery (Bing)
    if not results:
        results.extend(fetch_linkedin_via_google(company_name))

    print(f"\n[LINKEDIN] Total LinkedIn records: {len(results)}")
    return results
