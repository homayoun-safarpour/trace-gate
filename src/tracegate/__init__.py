"""trace-gate: score agent trajectories and gate deploys on a frozen baseline."""

from tracegate.baseline import Baseline, check_against_baseline, freeze_baseline
from tracegate.score import ScoreReport, score_trajectory
from tracegate.trajectory import Trajectory, load_trajectory

__all__ = [
    "Baseline",
    "ScoreReport",
    "Trajectory",
    "check_against_baseline",
    "freeze_baseline",
    "load_trajectory",
    "score_trajectory",
]

__version__ = "0.1.0"
