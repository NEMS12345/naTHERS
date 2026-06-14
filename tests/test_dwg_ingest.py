"""P2 DWG ingestion: ODA conversion gating + routing through the DXF adapter.

The DXF fixture stands in for the converted output, so these run without the ODA
File Converter or ezdxf-on-DWG being installed (but ezdxf is needed to read the
stand-in DXF).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("ezdxf")
pytest.importorskip("shapely")

from planassess.ingest.dwg import DWGAdapter, DWGConversionError  # noqa: E402

DXF_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_house.dxf"


def test_missing_oda_raises_clear_error():
    # ODA File Converter is not installed in this environment.
    adapter = DWGAdapter()
    with pytest.raises(DWGConversionError) as exc:
        adapter._converter()
    assert "ODA File Converter" in str(exc.value)


def test_conversion_disabled_in_config_raises(tmp_path: Path):
    from planassess.config.models import ODASettings, Settings

    adapter = DWGAdapter(settings=Settings(oda_file_converter=ODASettings(enabled=False)))
    with pytest.raises(DWGConversionError) as exc:
        adapter._converter()
    assert "disabled" in str(exc.value).lower()


def test_ingest_routes_converted_dxf_through_dxf_adapter(tmp_path: Path, monkeypatch):
    assert DXF_FIXTURE.exists(), "build the DXF fixture first"
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"fake-dwg")

    # Stand in for ODA: 'conversion' just yields our DXF fixture.
    def fake_convert(self, dwg_path: Path, out_dir: Path) -> Path:
        target = out_dir / "converted.dxf"
        shutil.copy2(DXF_FIXTURE, target)
        return target

    monkeypatch.setattr(DWGAdapter, "convert_to_dxf", fake_convert)

    model = DWGAdapter().ingest(dwg, "DWG-TEST")
    # Routed through the DXF adapter -> two rooms recovered.
    assert len(model.zones) == 2
    # Provenance records it came via the DWG path, with the true source file.
    assert model.extraction_meta.adapter == "dwg"
    assert model.extraction_meta.source_file == str(dwg)
