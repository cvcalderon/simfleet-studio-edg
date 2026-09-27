"""PART_B probability-calibration decision primitives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SigmoidCalibrationDecision:
    logloss_gain: float
    trip_day_share_error_worsening: float
    retained: bool


def sigmoid_calibration_decision(
    *,
    uncalibrated_logloss: float,
    calibrated_logloss: float,
    uncalibrated_share_error: float,
    calibrated_share_error: float,
    min_logloss_gain: float = 0.002,
    max_share_error_worsening: float = 0.005,
) -> SigmoidCalibrationDecision:
    gain = float(uncalibrated_logloss - calibrated_logloss)
    worsening = float(calibrated_share_error - uncalibrated_share_error)
    return SigmoidCalibrationDecision(
        logloss_gain=gain,
        trip_day_share_error_worsening=worsening,
        retained=(gain >= min_logloss_gain and worsening <= max_share_error_worsening),
    )
