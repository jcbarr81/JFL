from random import Random

from sim.ai_decision import OffenseContext, call_offense


def _distribution(context: OffenseContext, iterations: int = 1000, seed: int = 1234):
    rng = Random(seed)
    counts = {"run": 0, "pass": 0, "sideline_pass": 0}
    for _ in range(iterations):
        choice = call_offense(context, rng)
        counts[choice.category] += 1
    return {key: value / iterations for key, value in counts.items()}


def test_third_and_long_prefers_pass():
    ctx = OffenseContext(down=3, yards_to_first=9.0, yardline=50.0, remaining_time=400.0, score_diff=0)
    dist = _distribution(ctx)
    assert dist["pass"] + dist["sideline_pass"] >= 0.75


def test_third_and_short_prefers_run():
    ctx = OffenseContext(down=3, yards_to_first=1.5, yardline=40.0, remaining_time=600.0, score_diff=0)
    dist = _distribution(ctx)
    assert dist["run"] >= 0.6


def test_two_minute_trends_sideline_pass():
    ctx = OffenseContext(down=2, yards_to_first=6.0, yardline=45.0, remaining_time=90.0, score_diff=-3)
    dist = _distribution(ctx)
    assert dist["pass"] + dist["sideline_pass"] >= 0.8
    assert dist["sideline_pass"] >= 0.2
