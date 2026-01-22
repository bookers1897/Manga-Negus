"""
================================================================================
MangaNegus v3.0 - Lua Runtime
================================================================================
Python wrapper for Lua interpreter that provides FMD2-compatible API.

This module emulates the Free Manga Downloader (FMD2) Lua environment,
allowing us to run FMD's 590+ Lua source modules.

FMD API we emulate:
  - HTTP.GET(url) / HTTP.POST(url, data)
  - CreateTXQuery(html) for XPath parsing
  - NewWebsiteModule() for module registration
  - sleep(), print(), require()
  - LINKS, NAMES lists for results

Usage:
    runtime = LuaRuntime()
    module = runtime.load_module("MangaDex.lua")
    results = module.search("one piece")
================================================================================
"""

import json
import re
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
import requests
from bs4 import BeautifulSoup
from lxml import etree
import threading

# Try to import lupa
try:
    from lupa import LuaRuntime as LupaRuntime
    HAS_LUPA = True
except ImportError:
    HAS_LUPA = False
    print("WARNING: lupa not installed. Lua sources will not work.")


# =============================================================================
# FMD-COMPATIBLE CLASSES
# =============================================================================

class FMDHttpClient:
    """
    Emulates FMD's HTTP module.

    FMD API:
        HTTP.GET(url)        -> True/False, sets HTTP.Document
        HTTP.POST(url, data) -> True/False
        HTTP.UserAgent       -> String
        HTTP.Document        -> Response object with .ToString()
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.UserAgent = "MangaNegus/3.0"
        self.Document = None
        self.Cookies = ""
        self.Headers = {}
        self._last_response = None

        # Default headers
        self.session.headers.update({
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def GET(self, url: str) -> bool:
        """Perform GET request. Returns True on success."""
        try:
            headers = {"User-Agent": self.UserAgent}
            headers.update(self.Headers)

            response = self.session.get(url, headers=headers, timeout=30)
            self._last_response = response
            self.Document = FMDDocument(response.text)

            return response.status_code == 200
        except Exception as e:
            print(f"HTTP.GET error: {e}")
            self.Document = FMDDocument("")
            return False

    def POST(self, url: str, data: str = "") -> bool:
        """Perform POST request. Returns True on success."""
        try:
            headers = {"User-Agent": self.UserAgent}
            headers.update(self.Headers)

            # Try to parse data as JSON
            try:
                json_data = json.loads(data) if data else None
                response = self.session.post(url, json=json_data, headers=headers, timeout=30)
            except json.JSONDecodeError:
                response = self.session.post(url, data=data, headers=headers, timeout=30)

            self._last_response = response
            self.Document = FMDDocument(response.text)

            return response.status_code == 200
        except Exception as e:
            print(f"HTTP.POST error: {e}")
            self.Document = FMDDocument("")
            return False

    def Reset(self):
        """Reset HTTP state."""
        self.Document = None
        self.Headers = {}


class FMDDocument:
    """
    Emulates FMD's HTTP.Document object.

    FMD API:
        HTTP.Document.ToString() -> String (response body)
    """

    def __init__(self, content: str):
        self._content = content

    def ToString(self) -> str:
        return self._content

    def __str__(self) -> str:
        return self._content


class FMDXPathQuery:
    """
    Emulates FMD's CreateTXQuery for XPath/JSON parsing.

    FMD API:
        x = CreateTXQuery(html)
        x.XPath('//div[@class="title"]')
        x.XPathString('//div/text()')
        x.XPath('json(*)') for JSON parsing
    """

    def __init__(self, content: str):
        self._content = content
        self._json_data = None
        self._html_tree = None

        # Try to parse as JSON first
        try:
            self._json_data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass

        # Try to parse as HTML/XML
        try:
            # Wrap in root element for lxml
            wrapped = f"<root>{content}</root>"
            self._html_tree = etree.HTML(wrapped)
        except Exception:
            try:
                self._html_tree = etree.HTML(content)
            except Exception:
                pass

    def XPath(self, path: str, context=None) -> 'FMDXPathResult':
        """Execute XPath query."""
        # Handle JSON paths (FMD uses 'json(*)' syntax)
        if path.startswith('json('):
            return FMDXPathResult(self._json_data)

        # Handle JSON-style paths on context
        if context is not None and isinstance(context, (dict, list)):
            return self._query_json(path, context)

        # Standard XPath on HTML
        if self._html_tree is not None:
            try:
                results = self._html_tree.xpath(path)
                return FMDXPathResult(results)
            except Exception:
                pass

        return FMDXPathResult(None)

    def XPathString(self, path: str, context=None) -> str:
        """Execute XPath query and return string result."""
        result = self.XPath(path, context)
        return result.ToString()

    def _query_json(self, path: str, data: Any) -> 'FMDXPathResult':
        """Query JSON data with path-like syntax."""
        if data is None:
            return FMDXPathResult(None)

        # Handle paths like "attributes/title/*" or "id"
        parts = path.split('/')
        current = data

        for part in parts:
            if current is None:
                break

            if part == '*':
                # Return first value if dict
                if isinstance(current, dict) and current:
                    current = next(iter(current.values()))
                continue

            if part.endswith('()'):
                # Iterator syntax like "data()"
                key = part[:-2]
                if isinstance(current, dict) and key in current:
                    current = current[key]
                continue

            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                current = None

        return FMDXPathResult(current)


class FMDXPathResult:
    """Result from XPath query."""

    def __init__(self, data: Any):
        self._data = data

    def Get(self):
        """Return iterator for results."""
        if isinstance(self._data, list):
            return iter(self._data)
        elif self._data is not None:
            return iter([self._data])
        return iter([])

    def ToString(self) -> str:
        """Convert result to string."""
        if self._data is None:
            return ""
        if isinstance(self._data, str):
            return self._data
        if isinstance(self._data, (int, float)):
            return str(self._data)
        if isinstance(self._data, list):
            if len(self._data) == 0:
                return ""
            first = self._data[0]
            if hasattr(first, 'text'):
                return first.text or ""
            return str(first)
        if isinstance(self._data, dict):
            return json.dumps(self._data)
        if hasattr(self._data, 'text'):
            return self._data.text or ""
        return str(self._data)

    def __iter__(self):
        return self.Get()


class FMDList:
    """
    Emulates FMD's list objects (LINKS, NAMES).

    FMD API:
        LINKS.Add(link)
        NAMES.Add(name)
        LINKS.Count
    """

    def __init__(self):
        self._items: List[str] = []

    def Add(self, item: str):
        self._items.append(str(item))

    def Clear(self):
        self._items.clear()

    @property
    def Count(self) -> int:
        return len(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, idx: int) -> str:
        return self._items[idx]


class FMDWebsiteModule:
    """
    Emulates FMD's module object created by NewWebsiteModule().

    Properties:
        ID, Name, RootURL, Category
        OnGetNameAndLink, OnGetInfo, OnGetPageNumber
        MaxTaskLimit, MaxConnectionLimit
    """

    def __init__(self):
        self.ID = ""
        self.Name = ""
        self.RootURL = ""
        self.Category = ""
        self.OnGetNameAndLink = ""
        self.OnGetInfo = ""
        self.OnGetPageNumber = ""
        self.OnBeforeDownloadImage = ""
        self.MaxTaskLimit = 4
        self.MaxConnectionLimit = 4
        self._options = {}

    def AddOptionSpinEdit(self, key: str, label: str, default: int):
        self._options[key] = {"type": "spin", "label": label, "value": default}

    def AddOptionCheckBox(self, key: str, label: str, default: bool):
        self._options[key] = {"type": "checkbox", "label": label, "value": default}

    def AddOptionComboBox(self, key: str, label: str, items: str, default: int):
        self._options[key] = {"type": "combo", "label": label, "items": items.split('\r\n'), "value": default}


class FMDUpdateList:
    """Emulates FMD's UPDATELIST object for status updates."""

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        self._callback = callback

    def UpdateStatusText(self, text: str):
        if self._callback:
            self._callback(text)
        else:
            print(f"[Status] {text}")


# =============================================================================
# MAIN LUA RUNTIME
# =============================================================================

class LuaRuntime:
    """
    Main Lua runtime that provides FMD2-compatible environment.

    Usage:
        runtime = LuaRuntime()
        runtime.execute_file("modules/MangaDex.lua")
        runtime.call_function("Init")
        runtime.call_function("GetInfo")
    """

    def __init__(self, session: Optional[requests.Session] = None):
        if not HAS_LUPA:
            raise RuntimeError("lupa not installed. Run: pip install lupa")

        # Create Lua runtime
        self._lua = LupaRuntime(unpack_returned_tuples=True)

        # FMD-compatible objects
        self.HTTP = FMDHttpClient(session)
        self.LINKS = FMDList()
        self.NAMES = FMDList()
        self.UPDATELIST = FMDUpdateList()

        # Current URL (set before calling module functions)
        self.URL = ""

        # Loaded module
        self._module: Optional[FMDWebsiteModule] = None

        # Register globals
        self._setup_globals()

    def _setup_globals(self):
        """Set up FMD-compatible global variables and functions."""
        lua = self._lua
        g = lua.globals()

        # Secure Sandbox: Remove dangerous I/O and OS functions
        # This prevents RCE and file system access from malicious modules
        g.os = None
        g.io = None
        g.package = None
        g.dofile = None
        g.loadfile = None
        # keep require for FMD modules (we wrap it below)

        # Global objects
        g.HTTP = self.HTTP
        g.LINKS = self.LINKS
        g.NAMES = self.NAMES
        g.UPDATELIST = self.UPDATELIST

        # Global functions
        g.sleep = lambda ms: time.sleep(ms / 1000)
        g.print = print
        g.CreateTXQuery = lambda content: FMDXPathQuery(content)
        g.NewWebsiteModule = self._new_website_module

        # URL will be set dynamically
        g.URL = ""

        # Error codes
        g.no_error = 0
        g.net_problem = 1

        # Create 'require' function for FMD modules
        g.require = self._lua_require

        # String manipulation
        g.string = lua.globals().string  # Lua's string library

    def _new_website_module(self) -> FMDWebsiteModule:
        """Factory for NewWebsiteModule()."""
        self._module = FMDWebsiteModule()
        return self._module

    def _lua_require(self, module_name: str):
        """Emulate Lua's require() for FMD modules."""
        # Handle FMD's special modules
        if module_name == "fmd.env":
            return {"SelectedLanguage": "en"}

        if module_name == "fmd.crypto":
            # Return crypto helper
            return {
                "HTMLEncode": lambda s: s,  # Passthrough for now
                "HTMLDecode": lambda s: s,
            }

        # Default: try Lua's require
        return None

    def execute_file(self, filepath: str) -> bool:
        """Execute a Lua file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            self._lua.execute(code)
            return True
        except Exception as e:
            print(f"Error executing Lua file: {e}")
            return False

    def execute_code(self, code: str) -> bool:
        """Execute Lua code string."""
        try:
            self._lua.execute(code)
            return True
        except Exception as e:
            print(f"Error executing Lua code: {e}")
            return False

    def call_function(self, name: str, *args) -> Any:
        """Call a Lua function by name."""
        try:
            func = self._lua.globals()[name]
            if func is None:
                print(f"Function '{name}' not found")
                return None
            return func(*args)
        except Exception as e:
            print(f"Error calling '{name}': {e}")
            return None

    def set_url(self, url: str):
        """Set the current URL for module functions."""
        self.URL = url
        self._lua.globals().URL = url

    def get_module(self) -> Optional[FMDWebsiteModule]:
        """Get the loaded module (after Init() is called)."""
        return self._module

    def reset_lists(self):
        """Clear LINKS and NAMES lists."""
        self.LINKS.Clear()
        self.NAMES.Clear()

    def get_results(self) -> List[Dict[str, str]]:
        """Get paired results from LINKS and NAMES."""
        results = []
        for i in range(min(len(self.LINKS), len(self.NAMES))):
            results.append({
                "link": self.LINKS[i],
                "name": self.NAMES[i]
            })
        return results


# =============================================================================
# MODULE LOADER
# =============================================================================

class LuaModuleLoader:
    """
    Manages loading and caching of Lua modules.

    Usage:
        loader = LuaModuleLoader("sources/lua/modules")
        module = loader.load("MangaDex")
        results = module.search("one piece")
    """

    def __init__(self, modules_dir: str):
        self.modules_dir = modules_dir
        self._cache: Dict[str, LuaRuntime] = {}
        self._lock = threading.Lock()

    def list_modules(self) -> List[str]:
        """List available Lua modules."""
        import os
        modules = []
        if os.path.exists(self.modules_dir):
            for f in os.listdir(self.modules_dir):
                if f.endswith('.lua'):
                    modules.append(f[:-4])  # Remove .lua extension
        return sorted(modules)

    def load(self, module_name: str, session: Optional[requests.Session] = None) -> Optional[LuaRuntime]:
        """Load a Lua module by name."""
        import os

        filepath = os.path.join(self.modules_dir, f"{module_name}.lua")
        if not os.path.exists(filepath):
            print(f"Module not found: {filepath}")
            return None

        # Create new runtime for this module
        runtime = LuaRuntime(session)

        # Execute the module file
        if not runtime.execute_file(filepath):
            return None

        # Call Init() to register the module
        runtime.call_function("Init")

        return runtime

    def get_cached(self, module_name: str) -> Optional[LuaRuntime]:
        """Get cached module or None."""
        with self._lock:
            return self._cache.get(module_name)

    def cache_module(self, module_name: str, runtime: LuaRuntime):
        """Cache a loaded module."""
        with self._lock:
            self._cache[module_name] = runtime


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing Lua Runtime...")

    # Test basic functionality
    runtime = LuaRuntime()

    # Test executing Lua code
    runtime.execute_code("""
        function test_func()
            print("Hello from Lua!")
            return 42
        end
    """)

    result = runtime.call_function("test_func")
    print(f"Result: {result}")

    # Test HTTP
    print("\nTesting HTTP...")
    if runtime.HTTP.GET("https://api.mangadex.org/manga?limit=1"):
        doc = runtime.HTTP.Document.ToString()
        print(f"Got response: {len(doc)} bytes")

        # Test XPath/JSON parsing
        query = FMDXPathQuery(doc)
        result_status = query.XPathString("result", query._json_data)
        print(f"Status: {result_status}")

    print("\nLua Runtime tests complete!")
