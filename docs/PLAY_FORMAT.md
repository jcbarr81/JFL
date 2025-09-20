# Play Format

Gridiron plays are stored as JSON files that conform to `domain.models.Play`. The sample plays under `data/plays/` follow this structure and can be validated or imported through the `/play` API.

## Top-level fields

- `play_id` (string) - Stable identifier used for filenames and references.
- `name` (string) - Human readable label.
- `formation` (string) - Alignment descriptor (for example `Trips Left`). Max 64 characters.
- `personnel` (string) - Personnel grouping tag (for example `11`, `Nickel`). Max 32 characters.
- `play_type` (`"offense" | "defense" | "special_teams"`).
- `assignments` (array) - One object per participating player.

## Assignment objects

Each assignment describes one player:

- `player_id` (string) - Must match a `PlayerRow.player_id` in the roster.
- `role` (string) - One of `block`, `route`, `carry`, `pass`, `defend`, `rush`, `kick`, `hold`.
- `route` (null or array) - Waypoints the player should follow when the role requires movement.

### Role reference

| Role   | Typical usage                                   | Route required |
|--------|-------------------------------------------------|----------------|
| `pass` | Quarterback executing a dropback and throw      | No             |
| `carry`| Designed ball carrier on runs or screens        | No             |
| `route`| Receivers, tight ends, backs running routes     | Yes            |
| `block`| Offensive line, protectors, return team blockers| No             |
| `defend`| Coverage defenders dropping to a zone or man   | Yes            |
| `rush` | Edge/line rushers pursuing the QB               | Yes            |
| `kick` | Specialists kicking on special teams            | No             |
| `hold` | Placeholder/holder on special teams             | No             |

> Roles marked `Yes` must supply a `route` array. API validation rejects assignments that omit required routes or duplicate `player_id` values.

### Route points

Routes are lists of objects with the following fields:

- `timestamp` (float, seconds) - Elapsed time since the snap. Must be >= 0 and strictly increasing through the route.
- `x` (float, yards) - Horizontal displacement from the field center. Accepted range is -26.5 (left sideline) to 26.5 (right sideline).
- `y` (float, yards) - Vertical field position measured from the offense goal line. Accepted range is 0 to 120 (spans both end zones).

Include at least two points for meaningful motion; one point is treated as a spot drop.

## Built-in validation rules

The `/play/validate` endpoint and `/play/import` share the same checks:

- Every assignment must use a unique `player_id`.
- Roles flagged as requiring routes must provide a non-empty `route` list.
- Offense plays must have at least one `pass` or `carry` assignment, and no more than one `pass` assignment.
- Defense plays must include at least one `defend` or `rush` assignment.
- Special teams plays must include exactly one `kick` assignment.
- Route timestamps must increase strictly from point to point.

## Authoring workflow

1. Copy one of the samples in `data/plays/` as a starting point or build a payload in your editor of choice.
2. Run `POST /play/validate` with the JSON to confirm it passes structural checks.
3. Persist the play with `POST /play/import?overwrite=true` (writes to `data/plays/<play_id>.json`).
4. Call `GET /play/list` to confirm the play is discoverable by consumers.

## Example

```json
{
  "play_id": "slant_flat_left",
  "name": "Slant Flat Left",
  "formation": "Trips Left",
  "personnel": "11",
  "play_type": "offense",
  "assignments": [
    {"player_id": "QB1", "role": "pass", "route": null},
    {
      "player_id": "WR1",
      "role": "route",
      "route": [
        {"timestamp": 0.0, "x": 12.0, "y": 0.0},
        {"timestamp": 0.8, "x": 6.0, "y": 6.0},
        {"timestamp": 1.4, "x": 2.0, "y": 12.0}
      ]
    }
  ]
}
```

The engine expects 11 offensive and 11 defensive assignments in live play, but the schema does not enforce a hard count so that special packages (goal line, special teams) can vary. Use playbooks and test simulations to ensure assignments line up with roster positions.
