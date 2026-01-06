#!/usr/bin/env python3
"""
Test new manga site domains to find working alternatives
"""
import sys

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    print("⚠️ curl_cffi not installed. Install with: pip install curl_cffi")
    sys.exit(1)

from bs4 import BeautifulSoup

# Domains to test (based on 2025 migrations)
DOMAINS_TO_TEST = {
    "mangakakalot.gg": "https://mangakakalot.gg/search/story/naruto",
    "natomanga.com": "https://natomanga.com/search/story/naruto",
    "manganato.gg": "https://manganato.gg/search/story/naruto",
    "chapmanganato.com": "https://chapmanganato.com/search/story/naruto",
    "readmanganato.com": "https://readmanganato.com/search/story/naruto",
    "manganelo.com": "https://manganelo.com/search/story/naruto",
}

def test_domain(name, url):
    """Test if a domain is working and can return search results"""
    print(f"\n{'='*80}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print('='*80)

    session = curl_requests.Session()

    try:
        # Use curl_cffi with Chrome impersonation to bypass Cloudflare
        response = session.get(
            url,
            impersonate="chrome120",
            timeout=15,
            allow_redirects=True,
            headers={
                "Referer": f"https://{name}/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )

        print(f"✅ Status: {response.status_code}")

        # Check for redirects
        if response.url != url:
            print(f"⚠️ Redirected to: {response.url}")
            if "spinzywheel" in response.url or "casino" in response.url.lower():
                print(f"❌ DEAD DOMAIN - redirects to spam site")
                return False

        # Check for Cloudflare
        if "cloudflare" in response.text.lower() or "cf-challenge" in response.text:
            print(f"🛡️ Cloudflare detected (may need more advanced bypass)")

        # Parse results
        soup = BeautifulSoup(response.text, 'html.parser')

        # Try different selectors (different sites use different classes)
        selectors = [
            '.search-story-item',
            '.story-item',
            '.manga-item',
            '.item-img',
            'div[class*="story"]',
        ]

        results = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                print(f"✅ Found {len(items)} items with selector: {selector}")
                results = items
                break

        if not results:
            print(f"⚠️ No manga items found with any selector")
            print(f"Page title: {soup.title.text if soup.title else 'N/A'}")
            return False

        # Extract titles
        print(f"\n📚 Found manga:")
        for i, item in enumerate(results[:5], 1):
            title = None
            # Try different title extraction methods
            for method in [
                lambda x: x.select_one('img')['alt'] if x.select_one('img') else None,
                lambda x: x.select_one('.item-right h3 a').text if x.select_one('.item-right h3 a') else None,
                lambda x: x.select_one('a').get('title') if x.select_one('a') else None,
                lambda x: x.text.strip()[:50]
            ]:
                try:
                    title = method(item)
                    if title:
                        break
                except:
                    continue

            if title:
                print(f"  {i}. {title}")

        print(f"\n✅ WORKING DOMAIN: {name}")
        return True

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)[:100]}")
        return False

def main():
    print("="*80)
    print("MangaNegus Domain Migration Test")
    print("Testing alternative domains for shut-down sites")
    print("="*80)

    working = []
    broken = []

    for name, url in DOMAINS_TO_TEST.items():
        if test_domain(name, url):
            working.append(name)
        else:
            broken.append(name)

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print('='*80)
    print(f"\n✅ Working domains ({len(working)}):")
    for domain in working:
        print(f"  - {domain}")

    print(f"\n❌ Broken/Redirected domains ({len(broken)}):")
    for domain in broken:
        print(f"  - {domain}")

    if working:
        print(f"\n💡 Update sources to use: {working[0]}")

if __name__ == '__main__':
    main()
