"""Tests for ToolCallDetector._check_condition numeric operator handling.

Covers Bug 034 (PRM-TOL-019): _check_condition must return False (not raise
ValueError) when actual value is a non-numeric string and operator is
gt / gte / lt / lte.
"""

import pytest
from unittest.mock import MagicMock

from finbot.ctf.detectors.primitives.tool_call import ToolCallDetector


@pytest.fixture
def detector():
    d = ToolCallDetector.__new__(ToolCallDetector)
    d.config = {"tool_name": "test_tool"}
    d.challenge_id = "test"
    return d


class TestCheckConditionNumericOperators:
    """Bug 034: numeric operators should not raise on non-numeric strings."""

    @pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
    def test_non_numeric_actual_returns_false(self, detector, op):
        result = detector._check_condition("not_a_number", {op: 100})
        assert result is False

    @pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
    def test_non_numeric_expected_returns_false(self, detector, op):
        result = detector._check_condition(50, {op: "not_a_number"})
        assert result is False

    @pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
    def test_none_actual_returns_false(self, detector, op):
        result = detector._check_condition(None, {op: 100})
        assert result is False

    def test_gt_valid_numeric(self, detector):
        assert detector._check_condition(200, {"gt": 100}) is True
        assert detector._check_condition(50, {"gt": 100}) is False

    def test_gte_valid_numeric(self, detector):
        assert detector._check_condition(100, {"gte": 100}) is True
        assert detector._check_condition(99, {"gte": 100}) is False

    def test_lt_valid_numeric(self, detector):
        assert detector._check_condition(50, {"lt": 100}) is True
        assert detector._check_condition(200, {"lt": 100}) is False

    def test_lte_valid_numeric(self, detector):
        assert detector._check_condition(100, {"lte": 100}) is True
        assert detector._check_condition(101, {"lte": 100}) is False

    def test_string_numeric_actual_works(self, detector):
        """String representations of numbers should still compare correctly."""
        assert detector._check_condition("200", {"gt": 100}) is True
        assert detector._check_condition("50", {"gt": 100}) is False
