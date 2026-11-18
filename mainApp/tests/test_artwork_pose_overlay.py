import json
from pathlib import Path

from PIL import Image

from scripts.apply_pose_artwork_overlay import CONNECTIONS, JOINTS, render


EXPECTED_JOINTS = {
    f"{side}_{joint}"
    for side in ("left", "right")
    for joint in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
}


def test_pose_artwork_topology_has_twelve_bilateral_joints():
    assert JOINTS == EXPECTED_JOINTS
    assert len(CONNECTIONS) == 12

    for side in ("left", "right"):
        assert (f"{side}_hip", f"{side}_knee") in CONNECTIONS
        assert (f"{side}_knee", f"{side}_ankle") in CONNECTIONS
        assert not any(
            f"{side}_knee" in connection and "midpoint" in connection
            for connection in CONNECTIONS
        )


def test_checked_pose_specs_render_to_card_size(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "source.png"
    Image.new("RGB", (1536, 1024), "#152a32").save(source)

    for spec_path in sorted((root / "assets" / "hub_card_specs").glob("*.json")):
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
        assert payload["people"]
        assert all(set(person) == EXPECTED_JOINTS for person in payload["people"])
        assert all(len({tuple(point) for point in person.values()}) == 12 for person in payload["people"])

        output = tmp_path / f"{spec_path.stem}.jpg"
        render(source, spec_path, output)
        with Image.open(output) as rendered:
            assert rendered.size == (640, 360)
