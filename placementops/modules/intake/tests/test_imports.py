# @forgeplan-node: intake-module
"""
Tests for the import job lifecycle: upload, map-columns, validate, commit, get.

Covers: AC8, AC9, AC10, AC11, AC12
"""
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12

from __future__ import annotations

import io
import os
import struct
import uuid
import zipfile

import pytest
from sqlalchemy import select

from placementops.core.models import ImportJob
from placementops.modules.intake.service import check_zip_bomb
from placementops.modules.intake.tests.conftest import auth_headers

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers: build minimal XLSX bytes without openpyxl for testing uploads
# ---------------------------------------------------------------------------

def make_minimal_xlsx() -> bytes:
    """
    Create a minimal valid XLSX file in-memory using openpyxl (if available)
    or return a hardcoded minimal xlsx byte payload.
    """
    try:
        import openpyxl  # noqa: PLC0415
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["patient_name", "hospital_id"])
        ws.append(["John Test", str(uuid.uuid4())])
        ws.append(["Jane Test", str(uuid.uuid4())])
        ws.append(["Bob Test", str(uuid.uuid4())])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
    except ImportError:
        # Fallback: return a minimal xlsx-like zip (not parseable as real xlsx,
        # but sufficient for upload + content-type tests)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        return buf.getvalue()


def make_csv_bytes(rows: list[list[str]]) -> bytes:
    """Build CSV bytes from a list of rows."""
    lines = [",".join(row) for row in rows]
    return "\n".join(lines).encode("utf-8")


def make_zip_bomb() -> bytes:
    """Create a synthetic ZIP bomb payload (high ratio, low compressed size)."""
    buf = io.BytesIO()
    # Write a zero-byte file but report fake uncompressed size in infolist
    # Real zip bomb: compress highly compressible data
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Write 10 MB of zeros — compresses to tiny payload
        data = b"\x00" * (10 * 1024 * 1024)
        zf.writestr(zipfile.ZipInfo("xl/sharedStrings.xml"), data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# AC8: Upload — size limit, content-type, ZIP bomb detection, ImportJob created
# ---------------------------------------------------------------------------


async def test_upload_valid_xlsx_creates_import_job(
    client, db_session, seed_org, seed_intake_user
):
    """AC8: upload valid XLSX under 10 MB → 201, ImportJob.status==uploaded."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    xlsx_bytes = make_minimal_xlsx()

    resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={
            "file": (
                "test.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "uploaded"
    assert body["file_name"] == "test.xlsx"

    # Verify it's in DB
    result = await db_session.execute(
        select(ImportJob).where(ImportJob.id == body["id"])
    )
    job = result.scalar_one()
    assert job.status == "uploaded"


async def test_upload_oversized_file_returns_413(
    client, seed_org, seed_intake_user
):
    """AC8: upload 11 MB file → 413."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    # 11 MB of zeros — not a valid xlsx but size check should trigger first
    big_bytes = b"\x00" * (11 * 1024 * 1024)

    resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={
            "file": (
                "big.xlsx",
                big_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 413


async def test_upload_wrong_content_type_returns_415(
    client, seed_org, seed_intake_user
):
    """AC8: upload text/plain content-type → 415."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={
            "file": ("test.txt", b"hello world", "text/plain")
        },
    )
    assert resp.status_code == 415


async def test_upload_csv_valid(
    client, seed_org, seed_intake_user
):
    """AC8: upload valid CSV → 201, ImportJob.status==uploaded."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    csv_bytes = make_csv_bytes([
        ["patient_name", "hospital_id"],
        ["CSV Patient", str(uuid.uuid4())],
    ])

    resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={
            "file": ("test.csv", csv_bytes, "text/csv")
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "uploaded"


# ---------------------------------------------------------------------------
# ZIP bomb detection unit tests (service layer)
# ---------------------------------------------------------------------------


def test_check_zip_bomb_detects_high_ratio():
    """AC8: check_zip_bomb raises ValueError for high compression ratio payload."""
    # 5 MB of zeros — highly compressible
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        data = b"\x00" * (5 * 1024 * 1024)
        zf.writestr("xl/sharedStrings.xml", data)
    compressed = buf.getvalue()

    # Should raise because ratio >> 100
    with pytest.raises(ValueError, match="ZIP bomb"):
        check_zip_bomb(compressed, max_ratio=100.0, max_uncompressed=200 * 1024 * 1024)


def test_check_zip_bomb_passes_for_csv():
    """AC8: check_zip_bomb skips non-zip (CSV) data without raising."""
    csv_data = b"patient_name,hospital_id\nJohn,abc"
    check_zip_bomb(csv_data)  # Should not raise


def test_check_zip_bomb_passes_for_normal_xlsx():
    """AC8: check_zip_bomb passes for normally compressed XLSX."""
    xlsx_bytes = make_minimal_xlsx()
    if xlsx_bytes[:2] == b"PK":
        # Normal XLSX should pass zip bomb check
        check_zip_bomb(xlsx_bytes)  # Should not raise


# ---------------------------------------------------------------------------
# AC9: Map columns
# ---------------------------------------------------------------------------


async def test_map_columns_saves_mapping_and_advances_to_mapping_status(
    client, db_session, seed_org, seed_intake_user
):
    """AC9: POST /imports/{id}/map-columns → ImportJob.status==mapping, column_mapping_json stored."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )

    # First upload
    csv_bytes = make_csv_bytes([["patient_name", "hospital_id"], ["A", "B"]])
    upload_resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201
    import_id = upload_resp.json()["id"]

    # Map columns
    mapping_payload = {
        "mappings": [
            {"source_column": "patient_name", "destination_field": "patient_name"},
            {"source_column": "hospital_id", "destination_field": "hospital_id"},
        ]
    }
    resp = await client.post(
        f"/api/v1/imports/{import_id}/map-columns",
        headers=headers,
        json=mapping_payload,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "mapping"
    assert body["column_mapping_json"] is not None
    assert len(body["column_mapping_json"]["mappings"]) == 2


# ---------------------------------------------------------------------------
# AC10: Validate import
# ---------------------------------------------------------------------------


async def test_validate_import_returns_per_row_results_and_advances_to_ready(
    client, db_session, seed_org, seed_intake_user, seed_hospital
):
    """AC10: validate → per-row results, invalid row has error, ImportJob.status==ready."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )

    # Upload
    csv_bytes = make_csv_bytes([
        ["patient_name", "hospital_id"],
        ["Valid Patient", seed_hospital],
        ["Another Valid", seed_hospital],
        ["Third Patient", seed_hospital],
        ["", ""],  # Invalid: missing required fields
    ])
    upload_resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201
    import_id = upload_resp.json()["id"]

    # Map columns
    await client.post(
        f"/api/v1/imports/{import_id}/map-columns",
        headers=headers,
        json={
            "mappings": [
                {"source_column": "patient_name", "destination_field": "patient_name"},
                {"source_column": "hospital_id", "destination_field": "hospital_id"},
            ]
        },
    )

    # Validate
    resp = await client.post(
        f"/api/v1/imports/{import_id}/validate",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["total_rows"] == 4  # 3 valid + 1 invalid

    # Check per-row results
    row_results = body["row_results"]
    assert len(row_results) == 4

    valid_rows = [r for r in row_results if r["is_valid"]]
    invalid_rows = [r for r in row_results if not r["is_valid"]]
    assert len(valid_rows) == 3
    assert len(invalid_rows) == 1
    assert len(invalid_rows[0]["errors"]) > 0


# ---------------------------------------------------------------------------
# AC11: Commit import (background task)
# ---------------------------------------------------------------------------


async def test_commit_import_returns_202_immediately(
    client, db_session, seed_org, seed_intake_user, seed_hospital
):
    """AC11: POST /imports/{id}/commit → 202 immediately."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )

    csv_bytes = make_csv_bytes([
        ["patient_name", "hospital_id"],
        ["Commit Patient", seed_hospital],
    ])

    # Upload + map
    upload_resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    import_id = upload_resp.json()["id"]

    await client.post(
        f"/api/v1/imports/{import_id}/map-columns",
        headers=headers,
        json={
            "mappings": [
                {"source_column": "patient_name", "destination_field": "patient_name"},
                {"source_column": "hospital_id", "destination_field": "hospital_id"},
            ]
        },
    )

    resp = await client.post(
        f"/api/v1/imports/{import_id}/commit",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 202


async def test_commit_without_mapping_returns_400(
    client, seed_org, seed_intake_user
):
    """AC11: commit without column mapping set → 400."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    csv_bytes = make_csv_bytes([["patient_name"], ["Test"]])

    upload_resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    import_id = upload_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/imports/{import_id}/commit",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC12: GET /imports/{id}
# ---------------------------------------------------------------------------


async def test_get_import_job_returns_status_and_counts(
    client, db_session, seed_org, seed_intake_user
):
    """AC12: GET /imports/{id} → status, created_count, updated_count, failed_count present."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    csv_bytes = make_csv_bytes([["patient_name"], ["Test"]])

    upload_resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201
    import_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/imports/{import_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert "status" in body
    assert "created_count" in body
    assert "updated_count" in body
    assert "failed_count" in body
    assert body["status"] == "uploaded"


async def test_get_import_job_not_found(
    client, seed_org, seed_intake_user
):
    """AC12: GET /imports/{nonexistent_id} → 404."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/imports/{fake_id}", headers=headers)
    assert resp.status_code == 404
