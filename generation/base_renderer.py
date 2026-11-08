"""One renderer per output FORMAT (HTML, PDF, ...). The report TYPE is data: layouts.py.

So a new format is one new class here and one line in main.RENDERERS,
and a new report type is one new layout, without touching any renderer.
"""
from abc import ABC, abstractmethod
from pathlib import Path

from domain.models import AttendanceReport


class BaseRenderer(ABC):
    file_extension: str  # ".html", ".pdf"

    @abstractmethod
    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        """Write the report to output_path and return it. Never touches the source file."""
