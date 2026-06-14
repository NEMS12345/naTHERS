"""DWG ingestion adapter (P2 deliverable): convert to DXF, then reuse the DXF path.

DWG is a closed binary format, so PlanAssess relies on the free **ODA File
Converter** desktop tool (an external dependency) to convert DWG -> DXF, then
routes the result through :class:`~planassess.ingest.dxf.DXFAdapter`.

The converter is auto-invoked if present on PATH (or at the configured path). If
it is not installed, ingestion raises a clear, actionable error rather than
guessing — consistent with the no-silent-defaults rule.

ODA File Converter CLI (headless batch form)::

    ODAFileConverter <in_dir> <out_dir> <out_ver> <out_type> <recurse> <audit> [filter]

e.g. ``ODAFileConverter /in /out ACAD2018 DXF 0 1 *.dwg``
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config.loader import load_settings
from ..config.models import Settings
from ..model.building import BuildingModel
from .dxf import DXFAdapter


class DWGConversionError(RuntimeError):
    """Raised when DWG -> DXF conversion is unavailable or fails."""


class DWGAdapter:
    name = "dwg"

    def __init__(self, settings: Settings | None = None):
        self._settings = settings

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".dwg"

    def _converter(self) -> str:
        settings = self._settings or load_settings()
        oda = settings.oda_file_converter
        if not oda.enabled:
            raise DWGConversionError(
                "DWG conversion is disabled in config (oda_file_converter.enabled = false)."
            )
        exe = shutil.which(oda.executable) or (
            oda.executable if Path(oda.executable).exists() else None
        )
        if not exe:
            raise DWGConversionError(
                f"ODA File Converter ('{oda.executable}') was not found on PATH. Install the "
                "free ODA File Converter and ensure it is on PATH, or convert the DWG to DXF "
                "manually and ingest the DXF."
            )
        return exe

    def convert_to_dxf(self, dwg_path: Path, out_dir: Path) -> Path:
        """Run ODA File Converter to produce a DXF; return its path."""
        exe = self._converter()
        in_dir = out_dir / "in"
        conv_dir = out_dir / "out"
        in_dir.mkdir(parents=True, exist_ok=True)
        conv_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dwg_path, in_dir / dwg_path.name)

        cmd = [exe, str(in_dir), str(conv_dir), "ACAD2018", "DXF", "0", "1", "*.dwg"]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise DWGConversionError(f"ODA File Converter failed: {exc}") from exc

        produced = list(conv_dir.glob("*.dxf"))
        if not produced:
            raise DWGConversionError(
                "ODA File Converter ran but produced no DXF. Check the DWG is valid."
            )
        return produced[0]

    def ingest(self, path: Path, project_id: str) -> BuildingModel:
        with tempfile.TemporaryDirectory(prefix="planassess_dwg_") as tmp:
            dxf_path = self.convert_to_dxf(path, Path(tmp))
            model = DXFAdapter().ingest(dxf_path, project_id)
        # Record the true source and that it came via DWG conversion.
        model.extraction_meta.source_file = str(path)
        model.extraction_meta.adapter = self.name
        return model


def ingest_dwg(path: Path, project_id: str) -> BuildingModel:
    return DWGAdapter().ingest(path, project_id)
