from sqlalchemy import inspect
from sqlmodel import select, create_engine

import domain.db as db


def test_create_all_uses_configured_engine(tmp_path, monkeypatch) -> None:
    test_db_path = tmp_path / "gridiron-test.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False}
    )

    monkeypatch.setattr(db, "engine", test_engine, raising=False)

    db.create_all()

    assert test_db_path.exists()
    inspector = inspect(test_engine)
    expected_tables = {
        "playerrow",
        "teamrow",
        "seasonrow",
        "gamerow",
        "boxscorerow",
        "eventrow",
        "draftprospectrow",
    }
    assert expected_tables.issubset(set(inspector.get_table_names()))


def test_session_context_manager_commits_and_queries(tmp_path, monkeypatch) -> None:
    test_db_path = tmp_path / "gridiron-session.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(db, "engine", test_engine, raising=False)

    db.create_all()

    with db.get_session() as session:
        session.add(
            db.TeamRow(
                team_id="HOME",
                name="Home Team",
                city="Home City",
                abbreviation="HOM",
            )
        )

    with db.get_session() as session:
        result = session.exec(select(db.TeamRow)).all()

    assert [team.team_id for team in result] == ["HOME"]
