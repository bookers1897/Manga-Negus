/**
 * Utility Functions
 * Pure helper functions for XSS prevention, URL sanitization, and common operations
 */

export const PLACEHOLDER_IMAGE = '/static/images/placeholder.svg';

/**
 * Escape HTML to prevent XSS attacks
 * Uses textContent to safely escape HTML entities
 * @param {string} text - Text to escape
 * @returns {string} - HTML-escaped text
 */
export function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    // Safe approach: use textContent to set, then read the escaped result
    const div = document.createElement('div');
    const textNode = document.createTextNode(String(text));
    div.appendChild(textNode);
    return div.innerHTML;  // This is safe - we're reading, not writing untrusted content
}

/**
 * Sanitize URL to prevent javascript: protocol attacks
 * @param {string} url - URL to sanitize
 * @returns {string} - Sanitized URL or placeholder
 */
export function sanitizeUrl(url) {
    if (!url) return PLACEHOLDER_IMAGE;
    try {
        const parsed = new URL(url, window.location.origin);
        if (parsed.protocol === 'javascript:' || parsed.protocol === 'data:') {
            return PLACEHOLDER_IMAGE;
        }
        return url;
    } catch {
        return PLACEHOLDER_IMAGE;
    }
}

/**
 * Proxy external image URLs through backend to avoid CORS issues
 * @param {string} url - Image URL
 * @param {string} referer - Optional referer URL for CDN hotlink protection bypass
 * @returns {string} - Proxied URL or original if local
 */
export function proxyImageUrl(url, referer = null) {
    if (!url) return PLACEHOLDER_IMAGE;
    // If already a local URL, return as-is
    if (url.startsWith('/')) return url;
    // Proxy external URLs with optional referer
    let proxyUrl = `/api/proxy/image?url=${encodeURIComponent(url)}`;
    if (referer) {
        proxyUrl += `&referer=${encodeURIComponent(referer)}`;
    }
    return proxyUrl;
}

/**
 * Create a DOM element from HTML string (safe - uses DOMParser)
 * @param {string} html - HTML string
 * @returns {HTMLElement} - DOM element
 */
export function htmlToElement(html) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    return doc.body.firstChild;
}

/**
 * Debounce function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} - Debounced function
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
