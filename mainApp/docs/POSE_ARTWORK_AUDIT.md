# Pose artwork audit

AIHuMo person artwork follows one fixed 12-landmark graph per visible person:

- left/right shoulder, elbow, wrist, hip, knee, and ankle;
- shoulder-to-shoulder and hip-to-hip;
- same-side shoulder-to-hip;
- same-side shoulder → elbow → wrist; and
- same-side hip → knee → ankle.

Every landmark coordinate must be unique, including poses where a wrist touches an ankle. `apply_pose_artwork_overlay.py` rejects missing, extra, or duplicate locations before rendering.

## Deterministically rendered and verified

| Artwork | People | Verified landmarks |
| --- | ---: | ---: |
| Focus `graph_2d.jpg` | 1 | 12 |
| Focus `mirror_match.jpg` | 2 | 24 |
| Professional `pipeline.jpg` | 1 | 12 |
| Professional `ergonomics.jpg` | 1 | 12 |
| Professional `mirror_match.jpg` | 2 | 24 |
| Professional `avoid.jpg` | 1 | 12 |
| Professional `freeze.jpg` | 1 | 12 |
| Professional `mirror.jpg` | 2 | 24 |
| Professional `obstacle.jpg` | 1 | 12 |
| Professional `partner.jpg` | 2 | 24 |
| Professional `rhythm.jpg` | 1 | 12 |

Professional `alignment.jpg` intentionally uses abstract feature traces instead of tiny people, because 12 readable landmarks cannot be represented accurately at film-strip scale.

## Existing artwork visually rechecked

The following cards already showed 12 distinct, correctly sequenced landmarks and were retained: Focus `pipeline`, `just_dance`, `balance`, `sports`, `rehab`, `ergonomics`, and `gait`; Professional `just_dance`, `balance`, `gait`, `graph_2d`, `graph_3d`, `annotation`, `rehab`, and `sports`.

Run `pytest tests/test_artwork_pose_overlay.py` to validate every checked coordinate specification and render it at the required 640×360 card size.
