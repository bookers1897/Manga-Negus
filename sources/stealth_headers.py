"""
================================================================================
MangaNegus v2.3 - Stealth Headers
================================================================================
Generates consistent browser fingerprints to avoid bot detection.

The SessionFingerprint class creates a realistic browser profile that:
  - Stays consistent throughout a session (same UA, hints, etc.)
  - Includes modern Chrome client hints (Sec-CH-UA)
  - Randomizes header ordering to defeat fingerprinting
  - Provides separate header sets for JSON/HTML/image requests
================================================================================
"""

import random
from typing import Dict, List, Optional
from dataclasses import dataclass


# Browser profiles with matching client hints
BROWSER_PROFILES = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
        "platform": "Windows",
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
        "platform": "Windows",
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"macOS"',
        "platform": "macOS",
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"macOS"',
        "platform": "macOS",
    },
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Linux"',
        "platform": "Linux",
    },
]

# Accept-Language variations
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en,en-US;q=0.9",
]


@dataclass
class SessionFingerprint:
    """
    Generates and maintains a consistent browser fingerprint for a session.

    Once created, the fingerprint stays the same for all requests - this mimics
    how a real browser behaves (same UA, hints, etc. throughout a session).

    Usage:
        fingerprint = SessionFingerprint()
        headers = fingerprint.get_headers(referer="https://example.com")
    """

    user_agent: str = ""
    sec_ch_ua: str = ""
    sec_ch_ua_mobile: str = ""
    sec_ch_ua_platform: str = ""
    accept_language: str = ""
    platform: str = ""

    def __post_init__(self):
        """Initialize with random but consistent browser profile."""
        if not self.user_agent:
            profile = random.choice(BROWSER_PROFILES)
            self.user_agent = profile["ua"]
            self.sec_ch_ua = profile["sec_ch_ua"]
            self.sec_ch_ua_mobile = profile["sec_ch_ua_mobile"]
            self.sec_ch_ua_platform = profile["sec_ch_ua_platform"]
            self.platform = profile["platform"]
            self.accept_language = random.choice(ACCEPT_LANGUAGES)

    def get_headers(
        self,
        referer: Optional[str] = None,
        accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ) -> Dict[str, str]:
        """
        Get headers for a request with randomized ordering.

        Args:
            referer: Optional referer URL
            accept: Accept header value

        Returns:
            Dict of headers with randomized key ordering
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate",
            "Sec-CH-UA": self.sec_ch_ua,
            "Sec-CH-UA-Mobile": self.sec_ch_ua_mobile,
            "Sec-CH-UA-Platform": self.sec_ch_ua_platform,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none" if not referer else "same-origin",
            "Sec-Fetch-User": "?1",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
        }

        if referer:
            headers["Referer"] = referer

        # Randomize header order to defeat fingerprinting
        return self._randomize_order(headers)

    def get_json_headers(
        self,
        referer: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get headers for JSON API requests.

        Args:
            referer: Optional referer URL

        Returns:
            Dict of headers optimized for JSON requests
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate",
            "Sec-CH-UA": self.sec_ch_ua,
            "Sec-CH-UA-Mobile": self.sec_ch_ua_mobile,
            "Sec-CH-UA-Platform": self.sec_ch_ua_platform,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        if referer:
            headers["Referer"] = referer
            headers["Origin"] = self._extract_origin(referer)

        return self._randomize_order(headers)

    def get_image_headers(
        self,
        referer: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get headers for image requests.

        Args:
            referer: Optional referer URL

        Returns:
            Dict of headers optimized for image requests
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Accept-Encoding": "gzip, deflate",
            "Sec-CH-UA": self.sec_ch_ua,
            "Sec-CH-UA-Mobile": self.sec_ch_ua_mobile,
            "Sec-CH-UA-Platform": self.sec_ch_ua_platform,
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        if referer:
            headers["Referer"] = referer

        return self._randomize_order(headers)

    def _randomize_order(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Randomize header order while keeping critical headers first.

        Some headers should stay near the top (User-Agent, Accept), but the
        rest can be shuffled to avoid fingerprinting.
        """
        # Headers that should stay at the top
        priority_keys = ["User-Agent", "Accept", "Accept-Language", "Accept-Encoding"]

        # Split into priority and shuffleable
        priority = {k: headers[k] for k in priority_keys if k in headers}
        rest = {k: v for k, v in headers.items() if k not in priority_keys}

        # Shuffle the rest
        rest_keys = list(rest.keys())
        random.shuffle(rest_keys)
        shuffled_rest = {k: rest[k] for k in rest_keys}

        # Combine: priority first, then shuffled rest
        result = {}
        result.update(priority)
        result.update(shuffled_rest)

        return result

    def _extract_origin(self, url: str) -> str:
        """Extract origin (scheme + host) from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return url


# Convenience functions for quick header generation

def get_stealth_headers(referer: Optional[str] = None) -> Dict[str, str]:
    """
    Get a fresh set of stealth headers.

    Note: For session consistency, create a SessionFingerprint instance
    and reuse it instead of calling this function repeatedly.
    """
    return SessionFingerprint().get_headers(referer)


def get_json_headers(referer: Optional[str] = None) -> Dict[str, str]:
    """Get stealth headers for JSON requests."""
    return SessionFingerprint().get_json_headers(referer)


def get_image_headers(referer: Optional[str] = None) -> Dict[str, str]:
    """Get stealth headers for image requests."""
    return SessionFingerprint().get_image_headers(referer)


# Human-like timing jitter functions

def human_like_jitter(base_delay: float = 0.5) -> float:
    """
    Generate a human-like delay using log-normal distribution.

    Log-normal mimics how humans naturally vary in response time -
    usually quick, occasionally slow.

    Args:
        base_delay: Base delay in seconds

    Returns:
        Delay with human-like variation
    """
    # Log-normal parameters tuned for realistic browsing
    mu = -0.5
    sigma = 0.4
    jitter = random.lognormvariate(mu, sigma)
    return base_delay * jitter


def micro_jitter() -> float:
    """
    Generate a tiny random delay (50-200ms).

    Use between consecutive requests to appear more human.
    """
    return random.uniform(0.05, 0.2)
