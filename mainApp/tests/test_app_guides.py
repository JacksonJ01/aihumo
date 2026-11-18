import json

from PyQt6.QtWidgets import QFrame

from app.app_guides import APP_GUIDES, guides_markdown
from app.main_hub import MainHubDialog, hub_apps
from app.preferences import PreferenceStore


def test_every_hub_app_has_a_complete_guide():
    apps = hub_apps()
    assert {app.id for app in apps} == set(APP_GUIDES)
    for guide in APP_GUIDES.values():
        assert guide.purpose
        assert guide.before_you_start
        assert guide.steps
        assert guide.review
        assert guide.video_status


def test_guide_document_contains_every_current_app():
    apps = hub_apps()
    document = guides_markdown(apps)
    for app in apps:
        assert f"## {app.title}" in document
    assert "### Before you start" in document
    assert "### How to use" in document
    assert "Video guide coming soon." in document


def test_main_hub_exposes_guides_and_getting_started_panels(qt_app, tmp_path):
    dialog = MainHubDialog(state_dir=tmp_path)
    try:
        assert dialog.carousel_guide.text() == "How to use selected"
        assert all(card.guide_button.text() == "How to use" for grid in dialog.category_grids.values() for card in grid.cards)
        panels = [frame for frame in dialog.findChildren(QFrame) if frame.objectName() == "gettingStartedPanel"]
        assert len(panels) == len(dialog.NAV_ITEMS) - 1
    finally:
        dialog.close()


def test_legacy_vibrant_preference_migrates_to_focus_mode(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hub_artwork_style": "Vibrant"}), encoding="utf-8")
    assert PreferenceStore(path).values.hub_artwork_style == "Focus Mode"
