# @forgeplan-node: core-infrastructure
"""
Tests for PHI-safe logging — verifies PHILogFilter redacts known PHI field names.

Ensures that field names like patient_name, dob, mrn do not appear in log output.
"""

import logging
import pytest

from placementops.core.middleware import PHILogFilter, _PHI_FIELDS


def _make_logger_with_filter() -> tuple[logging.Logger, list[logging.LogRecord]]:
    """Create a test logger with PHILogFilter and a list-based handler."""
    records: list[logging.LogRecord] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(f"phi_test_{id(records)}")
    logger.setLevel(logging.DEBUG)
    logger.addFilter(PHILogFilter())
    logger.addHandler(CapturingHandler())
    return logger, records


def test_phi_field_name_redacted_in_message():
    """Log messages containing PHI field names have the field name redacted."""
    logger, records = _make_logger_with_filter()
    logger.info("Processing patient_name field from request")

    assert len(records) == 1
    # The raw message should have been redacted
    assert "patient_name" not in records[0].msg
    assert "[REDACTED_FIELD]" in records[0].msg


def test_mrn_field_redacted():
    """mrn field name is redacted from log messages."""
    logger, records = _make_logger_with_filter()
    logger.warning("Updating mrn for patient")

    assert "mrn" not in records[0].msg


def test_dob_field_redacted():
    """dob field name is redacted from log messages."""
    logger, records = _make_logger_with_filter()
    logger.error("Invalid dob format")

    assert "dob" not in records[0].msg


def test_non_phi_field_not_redacted():
    """Non-PHI field names like organization_id pass through unmodified."""
    logger, records = _make_logger_with_filter()
    logger.info("Processing request for organization_id abc123")

    assert "organization_id" in records[0].msg


def test_phi_filter_covers_all_defined_phi_fields():
    """Every field in _PHI_FIELDS is properly captured in the filter."""
    logger, records = _make_logger_with_filter()

    for field in _PHI_FIELDS:
        records.clear()
        logger.info(f"Testing field: {field} is present")
        assert len(records) == 1
        assert field not in records[0].msg, (
            f"PHI field '{field}' was not redacted from log message"
        )


def test_log_record_passes_through_when_no_phi():
    """Log records without PHI field names pass through unmodified."""
    logger, records = _make_logger_with_filter()
    logger.info("Case status changed from new to intake_in_progress")

    assert len(records) == 1
    assert records[0].msg == "Case status changed from new to intake_in_progress"


def test_phi_filter_allows_record_through_returns_true():
    """PHILogFilter.filter() always returns True (never suppresses records)."""
    phi_filter = PHILogFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="This has patient_name in it",
        args=(),
        exc_info=None,
    )
    result = phi_filter.filter(record)
    assert result is True
    assert "patient_name" not in record.msg
