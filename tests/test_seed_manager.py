from sim.seed import SeedManager


def test_seed_manager_deterministic() -> None:
    manager = SeedManager(base_seed=100)
    first = manager.game_seed("2025", 1, "HOME", "AWAY")
    second = manager.game_seed("2025", 1, "HOME", "AWAY")
    assert first == second


def test_seed_manager_uniqueness() -> None:
    manager = SeedManager(base_seed=1)
    seed_a = manager.game_seed("2025", 1, "A", "B")
    seed_b = manager.game_seed("2025", 1, "B", "A")
    assert seed_a != seed_b
