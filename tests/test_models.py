import pytest
from pydantic import ValidationError

from domain.models import (
    Assignment,
    Attributes,
    GameState,
    Player,
    Play,
    RoutePoint,
    Team,
)


def _attributes() -> Attributes:
    return Attributes(
        speed=90,
        strength=85,
        agility=88,
        awareness=80,
        catching=70,
        tackling=75,
        throwing_power=60,
        accuracy=65,
    )


def test_team_roster_default_factory_produces_unique_lists() -> None:
    team_one = Team(
        team_id="TEAM1",
        name="Team One",
        city="Testville",
        abbreviation="T1",
    )
    team_two = Team(
        team_id="TEAM2",
        name="Team Two",
        city="Mock City",
        abbreviation="T2",
    )

    assert team_one.roster == []
    assert team_two.roster == []
    assert team_one.roster is not team_two.roster


def test_attributes_enforces_rating_bounds() -> None:
    with pytest.raises(ValidationError):
        Attributes(
            speed=101,
            strength=90,
            agility=85,
            awareness=80,
            catching=75,
            tackling=70,
            throwing_power=65,
            accuracy=60,
        )


def test_assignment_requires_increasing_route_timestamps() -> None:
    with pytest.raises(ValidationError):
        Assignment(
            player_id="WR1",
            role="route",
            route=[
                RoutePoint(timestamp=0.0, x=0.0, y=0.0),
                RoutePoint(timestamp=0.5, x=3.0, y=5.0),
                RoutePoint(timestamp=0.4, x=6.0, y=10.0),
            ],
        )


def test_game_state_requires_valid_down_value() -> None:
    play = Play(
        play_id="P1",
        name="Test Play",
        formation="Shotgun",
        personnel="11",
        play_type="offense",
    )

    with pytest.raises(ValidationError):
        GameState(
            game_id="G1",
            offense_team_id="HOME",
            defense_team_id="AWAY",
            ball_on=50,
            down=5,
            yards_to_first=10,
            quarter=1,
            clock_seconds=600,
            play_clock=30,
            score_offense=7,
            score_defense=3,
            current_play=play,
        )


def test_player_model_holds_attributes_snapshot() -> None:
    attrs = _attributes()
    player = Player(
        player_id="PLAYER1",
        name="Test Player",
        position="QB",
        jersey_number=12,
        attributes=attrs,
    )

    assert player.attributes.speed == 90
    assert player.team_id is None
