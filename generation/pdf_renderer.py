"""Station 5, PDF: AttendanceReport -> PDF file, through the HTML of html_renderer.py.

Chromium (through Playwright) prints the HTML page to an A4 PDF. Chromium handles
Hebrew and right-to-left text the same way a browser shows it, so what you see in
the HTML is what you get in the PDF.

Which browser prints the page: the Chromium that Playwright downloads, and if it is
not there, a browser that is already installed (Edge comes with every Windows).
The order is in config/rules.py (PDF_BROWSER_CHANNELS). This matters where the
network blocks the Chromium download (for example a filter that replaces the
security certificates of websites): Edge needs no download at all.

Playwright is imported only when a PDF is made, so the rest of the program and the
tests work without it. One-time setup:
    pip install playwright
    python -m playwright install chromium     (optional when Edge or Chrome is installed)
"""
from pathlib import Path

from config.rules import PDF_BROWSER_CHANNELS
from domain.exceptions import GenerationError
from domain.models import AttendanceReport
from generation.base_renderer import BaseRenderer
from generation.html_renderer import HtmlRenderer

SETUP_HINT = (
    "Install Microsoft Edge or Google Chrome, or run once:  python -m playwright install chromium"
)


class PdfRenderer(BaseRenderer):
    file_extension = ".pdf"

    def __init__(
        self,
        html_renderer: HtmlRenderer | None = None,
        browser_channels: tuple[str | None, ...] = PDF_BROWSER_CHANNELS,
    ) -> None:
        self._html_renderer = html_renderer or HtmlRenderer()
        self._browser_channels = browser_channels

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        html = self._html_renderer.to_html(report)
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise GenerationError(f"Playwright is not installed. {SETUP_HINT}") from None

        with sync_playwright() as playwright:
            browser = self._launch_browser(playwright, PlaywrightError)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.pdf(path=str(output_path), prefer_css_page_size=True, print_background=True)
            except PlaywrightError as error:
                raise GenerationError(f"Could not create the PDF: {error}") from None
            finally:
                browser.close()
        return output_path

    def _launch_browser(self, playwright, playwright_error: type[Exception]):
        """The first browser in PDF_BROWSER_CHANNELS that starts. None = Playwright's own Chromium."""
        failures = []
        for channel in self._browser_channels:
            try:
                return playwright.chromium.launch(channel=channel) if channel else playwright.chromium.launch()
            except playwright_error as error:
                first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
                failures.append(f"{channel or 'Playwright Chromium'}: {first_line}")
        raise GenerationError("No browser could print the PDF (" + "; ".join(failures) + "). " + SETUP_HINT)
