"""Optimization utilities for migration conversion improvements."""

from lakeflow_migration_validator.optimization.adversarial_loop import (
    AdversarialLoop,
    LoopConfig,
    LoopEvent,
    LoopResult,
    RoundResult,
    export_as_golden_set,
)
from lakeflow_migration_validator.optimization.dspy_judge import (
    FAILURE_MODES,
    AgreementMetric,
    DSPyJudgeOptimizer,
    OptimizationResult,
    evaluate_judge_quality,
)
from lakeflow_migration_validator.optimization.judge_optimizer import (
    CalibrationPair,
    JudgeOptimizer,
    ManualCalibrator,
    create_calibrator,
    load_calibration_pairs,
)

__all__ = [
    # adversarial_loop
    "AdversarialLoop",
    "LoopConfig",
    "LoopEvent",
    "LoopResult",
    "RoundResult",
    "export_as_golden_set",
    # dspy_judge
    "AgreementMetric",
    "DSPyJudgeOptimizer",
    "FAILURE_MODES",
    "OptimizationResult",
    "evaluate_judge_quality",
    # judge_optimizer
    "CalibrationPair",
    "JudgeOptimizer",
    "ManualCalibrator",
    "create_calibrator",
    "load_calibration_pairs",
]
