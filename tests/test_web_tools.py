"""
Tests para las herramientas web de MILO (web_search y web_fetcher).
Todos los tests mockean requests para evitar peticiones reales a internet.
"""
import pytest
from unittest.mock import patch, Mock

from src.tools.web_search import web_search, _parse_duckduckgo_results, _strip_html_tags
from src.tools.web_fetcher import fetch_page, _html_to_text, _is_text_content


# ==============================================================================
# Fixtures y Helpers
# ==============================================================================

FAKE_DDG_HTML = """
<html>
<body>
<div class="result results_links results_links_deep web-result">
  <div class="links_main links_deep result__body">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle1&amp;rut=abc">
      First Result Title
    </a>
    <a class="result__url" href="https://example.com/article1">example.com/article1</a>
    <a class="result__snippet">This is the first result snippet with useful info.</a>
  </div>
</div>
<div class="result results_links results_links_deep web-result">
  <div class="links_main links_deep result__body">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fpage2&amp;rut=def">
      Second Result &amp; Title
    </a>
    <a class="result__url" href="https://example.org/page2">example.org/page2</a>
    <a class="result__snippet">The second snippet has <b>bold</b> text.</a>
  </div>
</div>
<div class="result results_links results_links_deep web-result">
  <div class="links_main links_deep result__body">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fthird.dev%2Fdocs&amp;rut=ghi">
      Third Result
    </a>
    <a class="result__url" href="https://third.dev/docs">third.dev/docs</a>
    <a class="result__snippet">Third snippet here.</a>
  </div>
</div>
</body>
</html>
"""

FAKE_HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
    <style>.hidden { display: none; }</style>
    <script>console.log("should be removed");</script>
</head>
<body>
    <nav><a href="/">Home</a><a href="/about">About</a></nav>
    <h1>Main Heading</h1>
    <p>This is the main content of the page.</p>
    <p>Second paragraph with <b>bold</b> and <i>italic</i> text.</p>
    <div>
        <h2>Subheading</h2>
        <p>More content here with &amp; entities &lt;escaped&gt;.</p>
    </div>
    <footer>Copyright 2024</footer>
</body>
</html>
"""


def _make_mock_response(text="", status_code=200, content_type="text/html; charset=utf-8"):
    """Helper to create a mock requests.Response."""
    mock_resp = Mock()
    mock_resp.text = text
    mock_resp.status_code = status_code
    mock_resp.headers = {"Content-Type": content_type}

    if status_code >= 400:
        http_error = __import__("requests").exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error
    else:
        mock_resp.raise_for_status.return_value = None

    return mock_resp


# ==============================================================================
# Tests para web_search
# ==============================================================================

class TestWebSearch:
    """Tests para la función web_search."""

    @patch("src.tools.web_search.requests.post")
    def test_search_returns_formatted_results(self, mock_post):
        """Verificar que web_search devuelve resultados formateados correctamente."""
        mock_post.return_value = _make_mock_response(text=FAKE_DDG_HTML)

        result = web_search("python tutorial")

        assert "Search results for: 'python tutorial'" in result
        assert "1." in result
        assert "2." in result
        assert "URL:" in result
        mock_post.assert_called_once()

    @patch("src.tools.web_search.requests.post")
    def test_search_respects_num_results(self, mock_post):
        """Verificar que num_results limita la cantidad de resultados."""
        mock_post.return_value = _make_mock_response(text=FAKE_DDG_HTML)

        result = web_search("test query", num_results=2)

        assert "1." in result
        assert "2." in result
        # No debería haber un tercer resultado
        assert "3." not in result

    def test_search_empty_query(self):
        """Verificar que una query vacía devuelve error."""
        result = web_search("")
        assert "Error" in result
        assert "empty" in result.lower()

    def test_search_whitespace_query(self):
        """Verificar que una query solo de espacios devuelve error."""
        result = web_search("   ")
        assert "Error" in result

    @patch("src.tools.web_search.requests.post")
    def test_search_timeout_error(self, mock_post):
        """Verificar manejo de timeout en la búsqueda."""
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("Connection timed out")

        result = web_search("timeout query")

        assert "Error" in result
        assert "timed out" in result.lower()

    @patch("src.tools.web_search.requests.post")
    def test_search_connection_error(self, mock_post):
        """Verificar manejo de error de conexión."""
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("No internet")

        result = web_search("offline query")

        assert "Error" in result
        assert "connect" in result.lower()

    @patch("src.tools.web_search.requests.post")
    def test_search_no_results(self, mock_post):
        """Verificar que devuelve mensaje apropiado cuando no hay resultados."""
        mock_post.return_value = _make_mock_response(text="<html><body>No results</body></html>")

        result = web_search("xyznonexistentquery12345")

        assert "No results found" in result

    @patch("src.tools.web_search.requests.post")
    def test_search_html_entities_decoded(self, mock_post):
        """Verificar que las entidades HTML se decodifican correctamente."""
        mock_post.return_value = _make_mock_response(text=FAKE_DDG_HTML)

        result = web_search("entities test")

        # "&amp;" en el título debería decodificarse a "&"
        assert "Second Result & Title" in result

    def test_search_num_results_clamped(self):
        """Verificar que num_results se limita entre 1 y 10."""
        # No debería lanzar excepciones con valores extremos
        with patch("src.tools.web_search.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(text=FAKE_DDG_HTML)
            result_min = web_search("test", num_results=-5)
            assert "Search results" in result_min or "No results" in result_min

            result_max = web_search("test", num_results=100)
            assert "Search results" in result_max or "No results" in result_max


# ==============================================================================
# Tests para web_fetcher
# ==============================================================================

class TestWebFetcher:
    """Tests para la función fetch_page."""

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_returns_clean_text(self, mock_get):
        """Verificar que fetch_page devuelve texto limpio sin HTML."""
        mock_get.return_value = _make_mock_response(text=FAKE_HTML_PAGE)

        result = fetch_page("https://example.com/test")

        assert "Main Heading" in result
        assert "main content" in result
        assert "<script>" not in result
        assert "<style>" not in result
        assert "console.log" not in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_removes_nav_and_footer(self, mock_get):
        """Verificar que se eliminan nav y footer."""
        mock_get.return_value = _make_mock_response(text=FAKE_HTML_PAGE)

        result = fetch_page("https://example.com/test")

        assert "Copyright 2024" not in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_decodes_entities(self, mock_get):
        """Verificar que las entidades HTML se decodifican."""
        mock_get.return_value = _make_mock_response(text=FAKE_HTML_PAGE)

        result = fetch_page("https://example.com/test")

        assert "& entities <escaped>" in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_truncation(self, mock_get):
        """Verificar que el contenido se trunca al límite de caracteres."""
        long_content = "<html><body><p>" + "A" * 5000 + "</p></body></html>"
        mock_get.return_value = _make_mock_response(text=long_content)

        result = fetch_page("https://example.com/long", max_chars=200)

        assert len(result) > 0
        assert "truncated" in result.lower()

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_no_truncation_when_short(self, mock_get):
        """Verificar que el contenido corto no se trunca."""
        short_content = "<html><body><p>Short content.</p></body></html>"
        mock_get.return_value = _make_mock_response(text=short_content)

        result = fetch_page("https://example.com/short", max_chars=8000)

        assert "truncated" not in result.lower()
        assert "Short content." in result

    def test_fetch_empty_url(self):
        """Verificar que una URL vacía devuelve error."""
        result = fetch_page("")
        assert "Error" in result
        assert "empty" in result.lower()

    def test_fetch_invalid_url_scheme(self):
        """Verificar que URLs sin http(s):// devuelven error."""
        result = fetch_page("ftp://example.com/file")
        assert "Error" in result
        assert "Invalid URL" in result

    def test_fetch_no_scheme_url(self):
        """Verificar que URLs sin esquema devuelven error."""
        result = fetch_page("example.com/page")
        assert "Error" in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_timeout_error(self, mock_get):
        """Verificar manejo de timeout al obtener una página."""
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout("Read timed out")

        result = fetch_page("https://example.com/slow")

        assert "Error" in result
        assert "timed out" in result.lower()

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_connection_error(self, mock_get):
        """Verificar manejo de error de conexión."""
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("DNS resolution failed")

        result = fetch_page("https://nonexistent.invalid/page")

        assert "Error" in result
        assert "connect" in result.lower()

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_http_404_error(self, mock_get):
        """Verificar manejo de HTTP 404."""
        mock_get.return_value = _make_mock_response(text="Not Found", status_code=404)

        result = fetch_page("https://example.com/missing")

        assert "Error" in result
        assert "404" in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_http_500_error(self, mock_get):
        """Verificar manejo de HTTP 500."""
        mock_get.return_value = _make_mock_response(text="Internal Server Error", status_code=500)

        result = fetch_page("https://example.com/broken")

        assert "Error" in result
        assert "500" in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_non_html_content_type(self, mock_get):
        """Verificar que se rechaza contenido no HTML (como imágenes o PDFs)."""
        mock_get.return_value = _make_mock_response(
            text="binary data",
            content_type="application/pdf"
        )

        result = fetch_page("https://example.com/doc.pdf")

        assert "Error" in result
        assert "text/HTML" in result or "Content-Type" in result

    @patch("src.tools.web_fetcher.requests.get")
    def test_fetch_empty_page_content(self, mock_get):
        """Verificar manejo de página sin contenido de texto."""
        empty_html = "<html><head><script>var x = 1;</script></head><body></body></html>"
        mock_get.return_value = _make_mock_response(text=empty_html)

        result = fetch_page("https://example.com/empty")

        assert "Warning" in result or "No readable" in result


# ==============================================================================
# Tests para funciones internas
# ==============================================================================

class TestInternalHelpers:
    """Tests para funciones internas auxiliares."""

    def test_strip_html_tags(self):
        """Verificar remoción de tags HTML."""
        assert _strip_html_tags("<b>bold</b>") == "bold"
        assert _strip_html_tags("<a href='#'>link</a>") == "link"
        assert _strip_html_tags("no tags") == "no tags"

    def test_strip_html_entities(self):
        """Verificar decodificación de entidades HTML."""
        result = _strip_html_tags("A &amp; B &lt; C &gt; D")
        assert result == "A & B < C > D"

    def test_html_to_text_removes_scripts(self):
        """Verificar que _html_to_text elimina scripts."""
        html = '<p>Hello</p><script>alert("bad")</script><p>World</p>'
        result = _html_to_text(html)
        assert "Hello" in result
        assert "World" in result
        assert "alert" not in result

    def test_html_to_text_preserves_paragraphs(self):
        """Verificar que _html_to_text mantiene estructura de párrafos."""
        html = "<p>Paragraph 1</p><p>Paragraph 2</p>"
        result = _html_to_text(html)
        assert "Paragraph 1" in result
        assert "Paragraph 2" in result

    def test_is_text_content(self):
        """Verificar detección de content-type textual."""
        assert _is_text_content("text/html; charset=utf-8") is True
        assert _is_text_content("text/plain") is True
        assert _is_text_content("application/xhtml+xml") is True
        assert _is_text_content("application/pdf") is False
        assert _is_text_content("image/png") is False

    def test_parse_ddg_empty_html(self):
        """Verificar que HTML vacío devuelve lista vacía."""
        results = _parse_duckduckgo_results("<html></html>", 5)
        assert results == []

    def test_parse_ddg_limits_results(self):
        """Verificar que se respeta el límite de resultados."""
        results = _parse_duckduckgo_results(FAKE_DDG_HTML, 1)
        assert len(results) <= 1
