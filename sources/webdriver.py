"""
================================================================================
MangaNegus v2.3 - Selenium WebDriver Manager
================================================================================
Centralized WebDriver management for Cloudflare bypass and JavaScript rendering.

Features:
  - Automatic ChromeDriver management
  - Headless browser support
  - Cookie persistence
  - Session reuse for efficiency
  - Proper cleanup
================================================================================
"""

import os
import time
import threading
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    webdriver = None

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WEBDRIVER_MANAGER = True
except ImportError:
    HAS_WEBDRIVER_MANAGER = False


class WebDriverManager:
    """
    Manages Selenium WebDriver instances for JavaScript-heavy sites.

    Usage:
        manager = WebDriverManager()

        # Get a driver instance
        with manager.get_driver() as driver:
            driver.get("https://example.com")
            html = driver.page_source

        # Or use the class methods
        html = manager.fetch_page("https://example.com")
        images = manager.get_images_from_page("https://example.com", "img.page")
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern for shared driver management."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._driver_pool: List[Any] = []  # webdriver.Chrome instances when available
        self._pool_lock = threading.Lock()
        self._max_pool_size = 3
        self._options = None
        self._cookies: Dict[str, List[Dict]] = {}  # Domain -> cookies

        self._setup_options()

    def _setup_options(self) -> None:
        """Configure Chrome options for headless operation."""
        if not HAS_SELENIUM:
            return

        self._options = Options()

        # Headless mode
        self._options.add_argument('--headless=new')
        self._options.add_argument('--disable-gpu')
        self._options.add_argument('--no-sandbox')
        self._options.add_argument('--disable-dev-shm-usage')

        # Performance optimizations
        self._options.add_argument('--disable-extensions')
        self._options.add_argument('--disable-infobars')
        self._options.add_argument('--disable-notifications')
        self._options.add_argument('--disable-popup-blocking')

        # Stealth settings to avoid detection
        self._options.add_argument('--disable-blink-features=AutomationControlled')
        self._options.add_experimental_option('excludeSwitches', ['enable-automation'])
        self._options.add_experimental_option('useAutomationExtension', False)

        # User agent
        self._options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # Disable images for faster loading (optional)
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'profile.default_content_setting_values.notifications': 2,
            'profile.managed_default_content_settings.stylesheets': 2,
        }
        # Uncomment to disable images:
        # self._options.add_experimental_option('prefs', prefs)

    def _create_driver(self) -> Optional[Any]:
        """Create a new WebDriver instance."""
        if not HAS_SELENIUM or webdriver is None:
            return None

        try:
            if HAS_WEBDRIVER_MANAGER:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=self._options)
            else:
                driver = webdriver.Chrome(options=self._options)

            # Execute stealth script
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })

            return driver
        except Exception as e:
            print(f"⚠️ Failed to create WebDriver: {e}")
            return None

    @contextmanager
    def get_driver(self):
        """
        Get a WebDriver instance from the pool.

        Usage:
            with manager.get_driver() as driver:
                driver.get(url)
        """
        driver = None

        # Try to get from pool
        with self._pool_lock:
            if self._driver_pool:
                driver = self._driver_pool.pop()

        # Create new if pool is empty
        if driver is None:
            driver = self._create_driver()

        if driver is None:
            raise RuntimeError("Failed to get WebDriver instance")

        try:
            yield driver
        finally:
            # Return to pool if under limit
            with self._pool_lock:
                if len(self._driver_pool) < self._max_pool_size:
                    self._driver_pool.append(driver)
                else:
                    driver.quit()

    def fetch_page(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        wait_timeout: int = 10,
        delay: float = 2.0
    ) -> Optional[str]:
        """
        Fetch a page with JavaScript rendering.

        Args:
            url: URL to fetch
            wait_selector: CSS selector to wait for (optional)
            wait_timeout: Timeout in seconds
            delay: Additional delay after page load

        Returns:
            Page HTML source or None on error
        """
        if not HAS_SELENIUM:
            return None

        try:
            with self.get_driver() as driver:
                driver.get(url)

                # Wait for specific element if requested
                if wait_selector:
                    try:
                        WebDriverWait(driver, wait_timeout).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                        )
                    except TimeoutException:
                        pass  # Continue anyway

                # Additional delay for dynamic content
                time.sleep(delay)

                return driver.page_source

        except Exception as e:
            print(f"⚠️ Failed to fetch page: {e}")
            return None

    def get_images_from_page(
        self,
        url: str,
        image_selector: str = "img",
        wait_timeout: int = 10,
        delay: float = 3.0
    ) -> List[str]:
        """
        Get all image URLs from a page.

        Args:
            url: URL to fetch
            image_selector: CSS selector for images
            wait_timeout: Timeout for page load
            delay: Delay after page load for lazy images

        Returns:
            List of image URLs
        """
        if not HAS_SELENIUM:
            return []

        try:
            with self.get_driver() as driver:
                driver.get(url)

                # Wait for images
                try:
                    WebDriverWait(driver, wait_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, image_selector))
                    )
                except TimeoutException:
                    pass

                # Scroll to load lazy images
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(delay)

                # Get all images
                images = driver.find_elements(By.CSS_SELECTOR, image_selector)
                urls = []

                for img in images:
                    src = img.get_attribute('src') or img.get_attribute('data-src')
                    if src and not src.startswith('data:'):
                        urls.append(src)

                return urls

        except Exception as e:
            print(f"⚠️ Failed to get images: {e}")
            return []

    def bypass_cloudflare(
        self,
        url: str,
        challenge_timeout: int = 15
    ) -> Optional[Dict[str, Any]]:
        """
        Bypass Cloudflare and get cookies + page content.

        Returns:
            Dict with 'cookies', 'html', and 'user_agent' or None on failure
        """
        if not HAS_SELENIUM:
            return None

        try:
            with self.get_driver() as driver:
                driver.get(url)

                # Wait for Cloudflare challenge to complete
                start_time = time.time()
                while time.time() - start_time < challenge_timeout:
                    # Check if we're past the challenge
                    if 'cf-browser-verification' not in driver.page_source:
                        if 'challenge-form' not in driver.page_source:
                            break
                    time.sleep(0.5)

                # Additional wait for page to fully load
                time.sleep(2)

                # Get cookies
                cookies = driver.get_cookies()

                # Store cookies for domain
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                self._cookies[domain] = cookies

                return {
                    'cookies': cookies,
                    'html': driver.page_source,
                    'user_agent': driver.execute_script("return navigator.userAgent")
                }

        except Exception as e:
            print(f"⚠️ Cloudflare bypass failed: {e}")
            return None

    def get_cookies_for_domain(self, domain: str) -> List[Dict]:
        """Get stored cookies for a domain."""
        return self._cookies.get(domain, [])

    def cleanup(self) -> None:
        """Clean up all WebDriver instances."""
        with self._pool_lock:
            for driver in self._driver_pool:
                try:
                    driver.quit()
                except Exception:
                    pass
            self._driver_pool.clear()

    def __del__(self):
        """Cleanup on destruction."""
        self.cleanup()


# Global instance
_webdriver_manager: Optional[WebDriverManager] = None


def get_webdriver_manager() -> WebDriverManager:
    """Get or create the global WebDriverManager instance."""
    global _webdriver_manager
    if _webdriver_manager is None:
        _webdriver_manager = WebDriverManager()
    return _webdriver_manager


def is_selenium_available() -> bool:
    """Check if Selenium is available."""
    return HAS_SELENIUM
