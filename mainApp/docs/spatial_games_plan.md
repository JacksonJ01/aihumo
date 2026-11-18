# AIHuMo Spatial Games Plan

## 1. Hot-and-Cold Reach Search

The core idea is a reach-search game where AIHuMo hides a target inside a calibrated reachable space. The player's wrist is the search pointer. Audio and visual feedback becomes warmer as the wrist approaches the target, and a target that remains unreachable for a configured period relocates automatically.

### Calibration levels

1. **2D screen space (recommended first version)**
   - Ask the player to reach left, right, high, and low while remaining visible.
   - Record robust wrist percentiles rather than one extreme frame, which prevents one tracking error from defining the play area.
   - Spawn targets inside the resulting reachable rectangle with a safety margin.
2. **2.5D reachable space**
   - Add near and far wrist samples.
   - Normalize image X/Y plus relative wrist depth against the player's own calibrated range.
   - Use a large capture radius because monocular depth is less stable than image position.
3. **True room-scale 3D**
   - Four image corners are insufficient: a volume also needs near/far limits. Use six bounds or eight sampled corners.
   - Prefer a depth camera, multiple calibrated cameras, or a tracked phone/controller. MediaPipe world coordinates from one RGB camera are useful estimates but are not a stable room coordinate system by themselves.

### Game progression

- Start with stationary targets and hot/cold distance cues.
- Add a visible capture radius and timeout relocation.
- Add a slow evading target whose speed is capped below the player's calibrated wrist speed.
- Preserve a guaranteed catch window: the target pauses, enters a boundary slowdown, or becomes capturable after a maximum chase time.

## 2. Phone Controller

The desktop app can host a small controller page and show a QR code. The phone joins a session using a short PIN and sends controls over a WebSocket. Buttons work on any modern browser; motion controls use the browser's orientation and motion APIs after the user grants permission.

Recommended sequence:

1. Local Wi-Fi controller with buttons and a session PIN.
2. Calibrated phone orientation represented as a quaternion, with recenter and sensitivity controls.
3. Shield mode using orientation and tilt.
4. Saber mode using angular velocity, swing direction, and a deliberate safety threshold.
5. Optional remote play through an authenticated hosted relay or WebRTC; localhost alone cannot connect a phone from another network.

The phone should send commands into the same input adapter as keyboard and pose controls. Game rules must not depend directly on a particular controller.

## 3. First Playable Prototype: Lane Dodge

- Three perspective lanes flow from a horizon toward the player.
- Obstacles spawn one lane at a time and accelerate gradually.
- Left/Right or A/D moves between lanes; Space starts or pauses; R resets.
- The pure game engine owns spawning, collision, scoring, lives, and difficulty.
- PyQt6 only handles rendering, sound cues, settings, and input.
- A later pose adapter can convert torso position into lane 0/1/2 without rewriting the game loop.
- A later phone adapter can emit the same left/right commands or continuous orientation values.
