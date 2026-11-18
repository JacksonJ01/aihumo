import pytest

from aihumo.lane_dodge import LaneDodgeEngine, LaneDodgeState


def test_lane_dodge_moves_within_three_lane_bounds():
    engine = LaneDodgeEngine()
    assert engine.snapshot().player_lane == 1
    engine.move(-1); engine.move(-1)
    assert engine.snapshot().player_lane == 0
    engine.move(1); engine.move(1); engine.move(1)
    assert engine.snapshot().player_lane == 2


def test_lane_dodge_collision_and_success_are_distinct():
    collision = LaneDodgeEngine(difficulty="easy")
    collision.start()
    collision.queue_obstacle(1, depth=0.895)
    hit = collision.step(0.05)
    assert hit.collisions == 1 and hit.lives == 3 and hit.dodged == 0

    dodge = LaneDodgeEngine(difficulty="easy")
    dodge.start()
    dodge.queue_obstacle(1, depth=0.895)
    dodge.move(-1)
    clear = dodge.step(0.5)
    assert clear.dodged == 1 and clear.collisions == 0
    assert clear.score == 100 and clear.streak == 1


def test_lane_dodge_game_over_reset_and_pause_are_safe():
    engine = LaneDodgeEngine(difficulty="hard")
    engine.start()
    for _ in range(3):
        engine.queue_obstacle(engine.player_lane, depth=0.899)
        engine.step(0.02)
    assert engine.state == LaneDodgeState.GAME_OVER
    assert engine.snapshot().lives == 0
    frozen = engine.step(1.0)
    assert frozen.elapsed_s < 1.0
    reset = engine.reset()
    assert reset.state == LaneDodgeState.READY.value and reset.lives == 3 and not reset.obstacles
    engine.start(); engine.pause()
    paused = engine.step(0.5)
    assert paused.elapsed_s == 0


def test_lane_dodge_is_seeded_and_rejects_invalid_inputs():
    first = LaneDodgeEngine(seed=4); second = LaneDodgeEngine(seed=4)
    first.start(); second.start()
    assert first.step(4.0).obstacles == second.step(4.0).obstacles
    with pytest.raises(ValueError, match="difficulty"):
        LaneDodgeEngine(difficulty="impossible")
    with pytest.raises(ValueError, match="backwards"):
        first.step(-0.1)
    with pytest.raises(ValueError, match="outside"):
        first.queue_obstacle(3)
