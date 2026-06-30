import re
import requests

# Headers para simular un navegador real
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

# Timeout global para peticiones HTTP (segundos)
_REQUEST_TIMEOUT = 15

# Tamaño máximo de descarga en bytes (5 MB) para evitar descargar archivos enormes
_MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024


def fetch_page(url: str, max_chars: int = 8000) -> str:
    """
    Fetch and extract readable text content from a web page.

    Downloads the HTML, strips tags/scripts/styles, and returns clean text
    truncated to max_chars.

    Args:
        url: The full URL to fetch, e.g., "https://example.com/article".
        max_chars: Maximum number of characters to return (default: 8000).

    Returns:
        The extracted text content of the page, or an error message if it fails.
    """
    if not url or not url.strip():
        return "Error: URL cannot be empty."

    url = url.strip()

    # Validar que la URL tiene un esquema válido
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return "Error: Invalid URL. Must start with http:// or https://."

    max_chars = max(100, min(max_chars, 50000))

    try:
        response = requests.get(
            url,
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()

        # Verificar que el content-type sea HTML/texto
        content_type = response.headers.get("Content-Type", "")
        if not _is_text_content(content_type):
            return f"Error: URL does not point to a text/HTML page (Content-Type: {content_type})."

        # Leer con límite de tamaño
        content = response.text[:_MAX_DOWNLOAD_BYTES]

    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {_REQUEST_TIMEOUT}s."
    except requests.exceptions.ConnectionError:
        return "Error: Could not connect to the URL. Check the address or your internet connection."
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        return f"Error: HTTP {status_code} when fetching URL."
    except requests.exceptions.RequestException as e:
        return f"Error fetching page: {str(e)}"

    text = _html_to_text(content)

    if not text.strip():
        return f"Warning: No readable text content found at {url}."

    # Truncar al límite
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n... [Content truncated to {0} chars]".format(max_chars)

    return text


def _is_text_content(content_type: str) -> bool:
    """Check if the Content-Type header indicates text/HTML content."""
    text_types = ["text/html", "text/plain", "application/xhtml", "application/xml", "text/xml"]
    content_type_lower = content_type.lower()
    return any(t in content_type_lower for t in text_types)


def _html_to_text(html: str) -> str:
    """
    Convert raw HTML to clean readable text using regex.

    Removes scripts, styles, navigation elements, and HTML tags while
    preserving meaningful text structure.

    Args:
        html: Raw HTML string.

    Returns:
        Clean text extracted from the HTML.
    """
    # Eliminar contenido de <script> y <style>
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Eliminar comentarios HTML
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # Eliminar nav, header, footer (contenido no principal)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Convertir <br>, <p>, <div>, headings a saltos de línea
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|h[1-6]|li|tr|blockquote)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<(p|div|h[1-6]|li|tr|blockquote)[^>]*>', '\n', text, flags=re.IGNORECASE)

    # Eliminar todas las etiquetas HTML restantes
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
        "&mdash;": "—",
        "&ndash;": "–",
        "&hellip;": "…",
        "&copy;": "©",
        "&reg;": "®",
        "&trade;": "™",
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)

    # Decodificar entidades numéricas &#NNN;
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))) if int(m.group(1)) < 0x110000 else '', text)

    # Limpiar whitespace excesivo
    text = re.sub(r'[ \t]+', ' ', text)           # Colapsar espacios horizontales
    text = re.sub(r'\n\s*\n', '\n\n', text)        # Máximo 1 línea en blanco
    text = re.sub(r'\n{3,}', '\n\n', text)         # Limitar saltos consecutivos

    return text.strip()
