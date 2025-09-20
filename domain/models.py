from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    confloat,
    conint,
    field_validator,
)

FootballPosition = Literal[
    "QB",
    "RB",
    "WR",
    "TE",
    "OL",
    "DL",
    "LB",
    "CB",
    "S",
    "K",
    "P",
]

AttributeRating = conint(ge=0, le=100)
RouteCoordinate = confloat(ge=-26.5, le=26.5)


class Attributes(BaseModel):
    """Scalar attributes that describe a player's physical and technical abilities."""

    speed: AttributeRating
    strength: AttributeRating
    agility: AttributeRating
    awareness: AttributeRating
    catching: AttributeRating
    tackling: AttributeRating
    throwing_power: AttributeRating = Field(
        ..., description="Passing velocity/power rating"
    )
    accuracy: AttributeRating


class Player(BaseModel):
    """Domain representation of a gridiron player."""

    player_id: str = Field(..., description="Unique identifier for the player")
    name: str
    position: FootballPosition
    jersey_number: conint(ge=0, le=99) = Field(..., description="Uniform jersey number")
    attributes: Attributes
    team_id: str | None = Field(
        default=None, description="Team identifier or None if unattached"
    )


class Team(BaseModel):
    """Team metadata and the roster of players."""

    team_id: str = Field(..., description="Unique identifier for the franchise")
    name: str
    city: str
    abbreviation: str = Field(..., min_length=2, max_length=4)
    roster: list[Player] = Field(default_factory=list, description="Active roster")


class RoutePoint(BaseModel):
    """A single waypoint in a player's route."""

    timestamp: confloat(ge=0) = Field(..., description="Seconds elapsed from snap")
    x: RouteCoordinate = Field(
        ..., description="Horizontal position (yards) from center of the field"
    )
    y: confloat(ge=0, le=120) = Field(
        ..., description="Vertical position (yards) from own end line"
    )


class Assignment(BaseModel):
    """Instruction given to a player for a specific play."""

    player_id: str
    role: Literal["block", "route", "carry", "pass", "defend", "rush", "kick", "hold"]
    route: list[RoutePoint] | None = Field(
        default=None, description="Route path when applicable"
    )

    @field_validator("route")
    @classmethod
    def validate_route_order(
        cls, route: list[RoutePoint] | None
    ) -> list[RoutePoint] | None:
        if route is None:
            return None
        if len(route) < 2:
            return route
        timestamps = [point.timestamp for point in route]
        for previous, current in zip(timestamps, timestamps[1:]):
            if current <= previous:
                raise ValueError("route timestamps must be strictly increasing")
        return route


class Play(BaseModel):
    """A named play with metadata and player assignments."""

    play_id: str
    name: str
    formation: str = Field(..., min_length=1, max_length=64)
    personnel: str = Field(..., min_length=1, max_length=32)
    play_type: Literal["offense", "defense", "special_teams"]
    assignments: list[Assignment] = Field(default_factory=list)


class GameState(BaseModel):
    """Snapshot of in-game context at a particular moment."""

    game_id: str
    offense_team_id: str
    defense_team_id: str
    ball_on: conint(ge=0, le=100) = Field(
        ..., description="Yard line relative to the offense"
    )
    down: Literal[1, 2, 3, 4]
    yards_to_first: confloat(gt=0, le=99.5)
    quarter: Literal[1, 2, 3, 4, 5] = Field(
        ..., description="Quarter number; 5 represents overtime"
    )
    clock_seconds: conint(ge=0, le=900) = Field(
        ..., description="Seconds remaining in the current quarter"
    )
    play_clock: conint(ge=0, le=40) = Field(
        ..., description="Seconds remaining on the play clock"
    )
    score_offense: conint(ge=0) = Field(..., description="Points scored by the offense")
    score_defense: conint(ge=0) = Field(..., description="Points scored by the defense")
    current_play: Play | None = Field(
        default=None, description="Play currently selected or in progress"
    )
