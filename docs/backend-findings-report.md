# Backend Code Quality & Security Audit

**Document ID:** BE-AUDIT-2026-001
**Date:** January 22, 2026
**Target:** MangaNegus Backend (`manganegus_app/`, `sources/`)
**Assessment Type:** Deep Dive Static Analysis

---

## 1. Executive Summary

This audit assesses the resilience, security, and maintainability of the MangaNegus backend. While the core architecture (Flask + Celery + SQLAlchemy) is sound, there are critical vulnerabilities in how download tasks handle file paths and how database connections are managed under load. The use of a "SmartSession" for bypassing anti-bot protections is clever but introduces fragility if upstream providers change their TLS fingerprinting detection.

**Overall Risk Rating:** **MEDIUM-HIGH**
*Functional logic is strong, but security controls around file system operations and database concurrency need immediate hardening.*

---

## 2. Vulnerability Details

### Finding #1: Path Traversal Risk in Download Handling
*   **Type:** Security (Arbitrary File Write)
*   **Severity:** **Critical**
*   **Location:** `manganegus_app/tasks/downloads.py`
*   **Description:** The download task uses `_sanitize_filename` but does not rigorously validate that the final path is strictly within the allowed `DOWNLOAD_DIR` before writing files.
*   **Impact:** A malicious source or manipulated manga title could theoretically craft a filename like `../../../etc/cron.d/evil` to write files outside the intended directory, potentially achieving Remote Code Execution (RCE).

### Finding #2: Database Connection Leaks (SQLite)
*   **Type:** Performance / Reliability
*   **Severity:** **High**
*   **Location:** `manganegus_app/database.py`
*   **Description:** The SQLite configuration uses `check_same_thread=False` without a strict connection pool limit or timeout strategy for write operations (WAL mode helps but isn't a silver bullet).
*   **Impact:** High concurrency (e.g., multiple users downloading simultaneously) can lead to `database is locked` errors, causing task failures and partial data writes.

### Finding #3: Implicit Trust in Source HTML
*   **Type:** Robustness
*   **Severity:** **Medium**
*   **Location:** `sources/weebcentral_v2.py` (and others)
*   **Description:** Connectors parse HTML using `BeautifulSoup` and assume elements exist. `link.select_one('img').get('alt')` will raise an `AttributeError` if the `img` tag is missing, crashing the entire search thread.
*   **Impact:** A layout change on a manga site will crash the search feature for *all* users until the code is patched.

### Finding #4: Race Conditions in Circuit Breaker
*   **Type:** Concurrency
*   **Severity:** **Medium**
*   **Location:** `sources/circuit_breaker.py`
*   **Description:** The `_half_open_calls` counter logic in `can_execute()` uses a lock, but the reset logic in `record_success` does not atomically check the state transition relative to other threads.
*   **Impact:** Under heavy load, more requests might be let through in the `HALF_OPEN` state than configured, potentially re-triggering bans from sensitive sources.

---

## 3. Remediation Steps

### 3.1. Security: Harden File Operations
**Goal:** Prevent Path Traversal.
**Action:** Enforce strict path resolution.

```python
# In tasks/downloads.py
def secure_path_join(base, *paths):
    final_path = os.path.abspath(os.path.join(base, *paths))
    if not final_path.startswith(os.path.abspath(base)):
        raise ValueError(f"Path traversal attempt: {final_path}")
    return final_path
```

### 3.2. Reliability: Defensive HTML Parsing
**Goal:** Prevent crashes on site changes.
**Action:** Use safe accessors (Monadic pattern or helper functions).

```python
# In sources/base.py
def safe_get_text(element, selector):
    el = element.select_one(selector)
    return el.get_text(strip=True) if el else None
```

### 3.3. Database: Enforce Connection Timeouts
**Goal:** Prevent locking.
**Action:** Update `create_db_engine` in `database.py`.

```python
engine = create_engine(
    db_url,
    connect_args={'timeout': 15}  # 15s wait for lock
)
```

### 3.4. Architecture: Task Idempotency
**Goal:** Ensure downloads can resume safely.
**Action:** Before starting a download task, check if the target `.cbz` already exists and matches the expected size (if known), skipping redundant work.

---

## 4. Appendix: Codebase Metrics

| Metric | Value | Status |
| :--- | :--- | :--- |
| **Download Logic** | ~300 LOC | ⚠️ Complex & Critical |
| **DB Models** | 8 Tables | ✅ Normalized |
| **Source Connectors** | Dynamic Loading | ✅ Extensible |

## 5. Conclusion

The backend is more robust than the frontend but has specific "hotspots" in file handling and external data parsing. Implementing the path security fix (#1) is the highest priority to ensure the "Download" feature is safe to use.
