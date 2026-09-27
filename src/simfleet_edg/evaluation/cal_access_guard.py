"""Explicit CAL/TEST opening guard used by F3.3c.

Pre-CAL entry points must leave both partitions closed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartitionAccess:
    cal_authorized: bool = False
    test_authorized: bool = False

    def require_cal(self) -> None:
        if not self.cal_authorized:
            raise PermissionError("CAL partition is UNOPENED by PRE-CAL gate")

    def require_test(self) -> None:
        if not self.test_authorized:
            raise PermissionError("TEST partition is SEALED")

    def assert_pre_cal(self) -> None:
        if self.cal_authorized or self.test_authorized:
            raise ValueError("PRE-CAL execution must not authorize CAL or TEST")
