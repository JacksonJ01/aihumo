"""Deterministic backend for the live three-lane dodge prototype.

The engine has no Qt dependency.  Rendering, keyboard input, pose input, and a
future phone controller can all drive the same small state machine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import random


class LaneDodgeState(str, Enum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    GAME_OVER = "game_over"


@dataclass(frozen=True)
class LaneObstacle:
    obstacle_id: int
    lane: int
    depth: float


@dataclass(frozen=True)
class LaneDodgeSnapshot:
    state: str
    player_lane: int
    lane_count: int
    obstacles: tuple[LaneObstacle, ...]
    score: int
    lives: int
    streak: int
    best_streak: int
    dodged: int
    collisions: int
    elapsed_s: float
    speed: float

    def to_document(self) -> dict:
        document = asdict(self)
        document["version"] = 1
        document["game_id"] = "lane_dodge"
        return document


class LaneDodgeEngine:
    """Advance obstacles toward a player occupying one of three lanes."""

    DIFFICULTY = {
        "easy": (0.46, 1.08, 1.42, 4),
        "medium": (0.57, 0.88, 1.24, 3),
        "hard": (0.70, 0.70, 1.02, 3),
    }

    def __init__(self, *, seed: int = 17, difficulty: str = "medium", lane_count: int = 3):
        if lane_count < 2:
            raise ValueError("Lane Dodge needs at least two lanes.")
        if difficulty not in self.DIFFICULTY:
            raise ValueError(f"Unknown Lane Dodge difficulty: {difficulty}")
        self.seed = int(seed)
        self.difficulty = difficulty
        self.lane_count = int(lane_count)
        self._rng = random.Random(self.seed)
        self.reset()

    def reset(self) -> LaneDodgeSnapshot:
        self._rng.seed(self.seed)
        self.state = LaneDodgeState.READY
        self.player_lane = self.lane_count // 2
        self.obstacles: list[LaneObstacle] = []
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.dodged = 0
        self.collisions = 0
        self.elapsed_s = 0.0
        self._next_obstacle_id = 1
        self._last_spawn_lane: int | None = None
        self._spawn_in_s = 1.15
        self.lives = self.DIFFICULTY[self.difficulty][3]
        return self.snapshot()

    @property
    def speed(self) -> float:
        base, _, _, _ = self.DIFFICULTY[self.difficulty]
        return base + min(0.30, self.elapsed_s * 0.004)

    def start(self) -> LaneDodgeSnapshot:
        if self.state == LaneDodgeState.GAME_OVER:
            self.reset()
        self.state = LaneDodgeState.RUNNING
        return self.snapshot()

    def pause(self) -> LaneDodgeSnapshot:
        if self.state == LaneDodgeState.RUNNING:
            self.state = LaneDodgeState.PAUSED
        return self.snapshot()

    def resume(self) -> LaneDodgeSnapshot:
        if self.state in {LaneDodgeState.READY, LaneDodgeState.PAUSED}:
            self.state = LaneDodgeState.RUNNING
        return self.snapshot()

    def move(self, direction: int) -> LaneDodgeSnapshot:
        if direction:
            self.player_lane = max(0, min(self.lane_count - 1, self.player_lane + (1 if direction > 0 else -1)))
        return self.snapshot()

    def queue_obstacle(self, lane: int, *, depth: float = 0.0) -> LaneObstacle:
        """Insert one obstacle for tests and future external game-rule drivers."""
        if not 0 <= lane < self.lane_count:
            raise ValueError("Obstacle lane is outside the board.")
        if not 0.0 <= depth <= 1.2:
            raise ValueError("Obstacle depth must be between 0.0 and 1.2.")
        obstacle = LaneObstacle(self._next_obstacle_id, int(lane), float(depth))
        self._next_obstacle_id += 1
        self.obstacles.append(obstacle)
        return obstacle

    def _spawn_obstacle(self) -> None:
        choices = list(range(self.lane_count))
        if self._last_spawn_lane in choices and len(choices) > 1:
            choices.remove(self._last_spawn_lane)
        lane = self._rng.choice(choices)
        self.queue_obstacle(lane)
        self._last_spawn_lane = lane
        _, minimum, maximum, _ = self.DIFFICULTY[self.difficulty]
        # Difficulty increases gently, but the interval never drops below the
        # tested reaction-time floor for a single-lane keyboard transition.
        scale = max(0.82, 1.0 - self.elapsed_s * 0.0015)
        self._spawn_in_s += self._rng.uniform(minimum, maximum) * scale

    def step(self, delta_s: float) -> LaneDodgeSnapshot:
        if delta_s < 0:
            raise ValueError("Lane Dodge time cannot move backwards.")
        if self.state != LaneDodgeState.RUNNING or delta_s == 0:
            return self.snapshot()
        # Substeps keep collision checks reliable if a busy UI delivers a
        # delayed timer event.  A single frame can never tunnel through the
        # player merely because the desktop paused briefly.
        remaining = min(float(delta_s), 1.0)
        while remaining > 1e-9 and self.state == LaneDodgeState.RUNNING:
            step_s = min(remaining, 1 / 60)
            self._advance(step_s)
            remaining -= step_s
        return self.snapshot()

    def _advance(self, delta_s: float) -> None:
        self.elapsed_s += delta_s
        self._spawn_in_s -= delta_s
        while self._spawn_in_s <= 0:
            self._spawn_obstacle()

        updated: list[LaneObstacle] = []
        for obstacle in self.obstacles:
            depth = obstacle.depth + self.speed * delta_s
            if depth >= 0.90 and obstacle.lane == self.player_lane:
                self.collisions += 1
                self.lives = max(0, self.lives - 1)
                self.streak = 0
                if self.lives <= 0:
                    self.state = LaneDodgeState.GAME_OVER
                continue
            if depth >= 1.06:
                self.dodged += 1
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                self.score += 100 + min(250, (self.streak - 1) * 10)
                continue
            updated.append(LaneObstacle(obstacle.obstacle_id, obstacle.lane, depth))
        self.obstacles = updated

    def snapshot(self) -> LaneDodgeSnapshot:
        return LaneDodgeSnapshot(
            state=self.state.value,
            player_lane=self.player_lane,
            lane_count=self.lane_count,
            obstacles=tuple(self.obstacles),
            score=self.score,
            lives=self.lives,
            streak=self.streak,
            best_streak=self.best_streak,
            dodged=self.dodged,
            collisions=self.collisions,
            elapsed_s=self.elapsed_s,
            speed=self.speed,
        )
