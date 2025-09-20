import json
from pathlib import Path

from sqlmodel import create_engine, select

import domain.db as db
from domain.db import PlayerRow, TeamRow
from domain.models import Play
from scripts import seed_league


def test_seed_league_creates_expected_records(tmp_path, monkeypatch) -> None:
    test_db_path = tmp_path / "gridiron.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(db, "engine", test_engine, raising=False)

    plays_dir = tmp_path / "plays"

    summary = seed_league.seed_league(seed=1234, plays_dir=plays_dir)

    assert summary.teams == len(seed_league.TEAM_DEFINITIONS)
    assert summary.players == len(seed_league.TEAM_DEFINITIONS) * seed_league.PLAYERS_PER_TEAM
    assert summary.plays_written == len(seed_league.SAMPLE_PLAYS)

    with db.get_session() as session:
        team_ids = session.exec(select(TeamRow.team_id)).all()
        player_count = session.exec(select(PlayerRow)).all()

    assert set(team_ids) == {team["team_id"] for team in seed_league.TEAM_DEFINITIONS}
    assert len(player_count) == summary.players

    play_files = list(plays_dir.glob("*.json"))
    assert len(play_files) == summary.plays_written

    for play_path in play_files:
        data = json.loads(play_path.read_text(encoding="utf-8"))
        Play.model_validate(data)

    # Idempotency: running twice does not duplicate entries
    seed_league.seed_league(seed=9999, plays_dir=plays_dir)

    with db.get_session() as session:
        teams_after = session.exec(select(TeamRow.team_id)).all()
        players_after = session.exec(select(PlayerRow)).all()

    assert set(teams_after) == set(team_ids)
    assert len(players_after) == len(player_count)
