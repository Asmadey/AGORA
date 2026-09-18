"""Real PDF/XLSX files exercise the worker extraction seam."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.portraits.extract import ContextExtractionError, extract_context_text


def _write_pdf(path: Path, text: str) -> None:
    """Write a tiny valid PDF without making reportlab a worker dependency."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 18 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(payload)


def test_real_pdf_text_is_extracted(tmp_path: Path) -> None:
    pytest.importorskip("pdfminer")
    path = tmp_path / "audience.pdf"
    _write_pdf(path, "Audience likes quiet historical stories")

    assert extract_context_text(path) == "Audience likes quiet historical stories"


def test_real_xlsx_cells_are_extracted_and_capped(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "Niche"
    sheet["B1"] = "historical cinema"
    sheet["A2"] = "Vocabulary"
    sheet["B2"] = "quiet, precise, archival"
    path = tmp_path / "audience.xlsx"
    workbook.save(path)
    workbook.close()

    text = extract_context_text(path)
    assert "historical cinema" in text
    assert "quiet, precise, archival" in text
    assert "\t" in text


def test_empty_pdf_text_layer_is_a_loud_failure(tmp_path: Path) -> None:
    pytest.importorskip("pdfminer")
    path = tmp_path / "scan.pdf"
    _write_pdf(path, "")

    with pytest.raises(ContextExtractionError, match="не извлечено"):
        extract_context_text(path)


def test_legacy_xls_names_the_reason_and_the_fix(tmp_path: Path) -> None:
    """
    `.xls` отклоняется с объяснением, а не падает внутри openpyxl.

    openpyxl читает только OOXML. Без этой ветки старая книга роняла бы разбор
    невнятным InvalidFileException уже внутри оплаченного прогона, и причина
    «не тот формат Excel» не прозвучала бы нигде.
    """
    path = tmp_path / "аудитория.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

    with pytest.raises(ContextExtractionError, match="xlsx"):
        extract_context_text(path)
