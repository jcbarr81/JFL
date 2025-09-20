from sim.calibration import run_calibration
from sim.ruleset import TUNING


def test_run_calibration_produces_metrics() -> None:
    report = run_calibration(seasons=1, team_count=4, base_seed=0)
    assert report.league_averages
    assert "completion_pct" in report.league_averages
    assert "penalties" in report.league_averages

    suggestions = report.suggestions
    assert "penalty_rate_mod" in suggestions
    assert suggestions["penalty_rate_mod"]["current"] == round(TUNING.penalty_rate_mod, 4)
