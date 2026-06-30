import re
import requests

# Headers para simular un navegador real y evitar bloqueos
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

# Timeout global para peticiones HTTP (segundos)
_REQUEST_TIMEOUT = 10


def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo HTML interface (no API key required).

    Args:
        query: The search query string, e.g., "Python asyncio tutorial".
        num_results: Maximum number of results to return (default: 5, max: 10).

    Returns:
        A formatted string with numbered search results (title + URL + snippet),
        or an error message if the search fails.
    """
    if not query or not query.strip():
        return "Error: Search query cannot be empty."

    num_results = max(1, min(num_results, 10))

    try:
        url = "https://html.duckduckgo.com/html/"
        response = requests.post(
            url,
            data={"q": query},
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        html = response.text
    except requests.exceptions.Timeout:
        return f"Error: Search request timed out after {_REQUEST_TIMEOUT}s."
    except requests.exceptions.ConnectionError:
        return "Error: Could not connect to search engine. Check your internet connection."
    except requests.exceptions.RequestException as e:
        return f"Error performing web search: {str(e)}"

    results = _parse_duckduckgo_results(html, num_results)

    if not results:
        return f"No results found for: '{query}'"

    lines = [f"Search results for: '{query}'\n"]
    for i, result in enumerate(results, 1):
        lines.append(f"{i}. {result['title']}")
        lines.append(f"   URL: {result['url']}")
        if result["snippet"]:
            lines.append(f"   {result['snippet']}")
        lines.append("")

    return "\n".join(lines).strip()


def _parse_duckduckgo_results(html: str, max_results: int) -> list:
    """
    Parse DuckDuckGo HTML search results using regex.

    Args:
        html: Raw HTML response from DuckDuckGo.
        max_results: Maximum number of results to extract.

    Returns:
        A list of dicts with keys: 'title', 'url', 'snippet'.
    """
    results = []

    # Each result lives inside a <div class="result ..."> block
    result_blocks = re.findall(
        r'<div[^>]*class="[^"]*result[^"]*results_links[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html,
        re.DOTALL,
    )

    # Fallback: buscar enlaces de resultado directamente si no se encuentran bloques
    if not result_blocks:
        result_blocks = re.findall(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>.*?</a>.*?(?:<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>.*?</a>)?',
            html,
            re.DOTALL,
        )

    for block in result_blocks[:max_results]:
        title = _extract_title(block)
        url = _extract_url(block)
        snippet = _extract_snippet(block)

        # Solo incluir resultados con al menos título o URL válidos
        if title or url:
            results.append({
                "title": title or "(Sin título)",
                "url": url or "(URL no disponible)",
                "snippet": snippet,
            })

    return results


def _extract_title(block: str) -> str:
    """Extract the title from a result block."""
    match = re.search(r'class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
    if match:
        return _strip_html_tags(match.group(1)).strip()
    return ""


def _extract_url(block: str) -> str:
    """Extract the URL from a result block."""
    match = re.search(r'class="[^"]*result__url[^"]*"[^>]*href="([^"]*)"', block, re.DOTALL)
    if match:
        url = match.group(1).strip()
        if url.startswith("//"):
            url = "https:" + url
        return url

    # Fallback: extraer href del enlace principal
    match = re.search(r'class="[^"]*result__a[^"]*"[^>]*href="([^"]*)"', block, re.DOTALL)
    if match:
        url = match.group(1).strip()
        # DuckDuckGo a veces usa redirects, extraer la URL real
        uddg_match = re.search(r'uddg=([^&]+)', url)
        if uddg_match:
            from urllib.parse import unquote
            return unquote(uddg_match.group(1))
        if url.startswith("//"):
            url = "https:" + url
        return url

    return ""


def _extract_snippet(block: str) -> str:
    """Extract the snippet/description from a result block."""
    match = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
    if not match:
        match = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
    if match:
        return _strip_html_tags(match.group(1)).strip()
    return ""


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags and decode common HTML entities."""
    text = re.sub(r'<[^>]+>', '', text)
    # Decodificar entidades HTML comunes
    replacements = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&nbsp;": " ",
        "&#x27;": "'",
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)
    # Colapsar whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
