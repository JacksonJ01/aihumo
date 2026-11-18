from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from app.lane_dodge_game import LaneDodgeDialog
from aihumo.lane_dodge import LaneDodgeState


def test_lane_dodge_keyboard_actions_render_and_control_loop(qt_app):
    dialog = LaneDodgeDialog()
    try:
        dialog.show()
        qt_app.processEvents()
        assert dialog.engine.player_lane == 1
        QTest.keyClick(dialog, Qt.Key.Key_Right)
        assert dialog.engine.player_lane == 2
        QTest.keyClick(dialog, Qt.Key.Key_Left)
        assert dialog.engine.player_lane == 1
        QTest.keyClick(dialog, Qt.Key.Key_Space)
        assert dialog.engine.state == LaneDodgeState.RUNNING and dialog.timer.isActive()
        dialog.timer.stop()
        dialog._tick()
        assert dialog.engine.elapsed_s > 0
        QTest.keyClick(dialog, Qt.Key.Key_Space)
        assert dialog.engine.state == LaneDodgeState.PAUSED
        QTest.keyClick(dialog, Qt.Key.Key_R)
        assert dialog.engine.state == LaneDodgeState.READY
        assert not dialog.canvas.grab().isNull()
    finally:
        dialog.close()


def test_lane_dodge_difficulty_and_controller_neutral_actions(qt_app):
    dialog = LaneDodgeDialog()
    try:
        dialog.handle_action("left")
        assert dialog.engine.player_lane == 0
        dialog.difficulty.setCurrentIndex(dialog.difficulty.findData("hard"))
        assert dialog.engine.difficulty == "hard"
        assert dialog.engine.player_lane == 1
        dialog.handle_action("right")
        assert dialog.engine.player_lane == 2
        dialog.handle_action("toggle")
        dialog.timer.stop()
        assert dialog.engine.state == LaneDodgeState.RUNNING
        dialog.handle_action("reset")
        assert dialog.engine.state == LaneDodgeState.READY
    finally:
        dialog.close()
