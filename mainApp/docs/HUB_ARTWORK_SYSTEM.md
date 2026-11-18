# AIHuMo Hub artwork system

The Hub maintains two complete, interchangeable card libraries:

- **Focus Mode** uses simplified editorial illustrations, a restrained cross-theme palette, and one clear concept per card.
- **Professional** uses restrained color, realistic materials, one focal action, and less visual noise for an adult health-tech audience.

Both libraries use the same filenames and 640×360 canvas. The Hub therefore changes style without changing app identity, navigation, copy, or behavior. Users can switch from the Hub navigation bar or choose a persistent default in **Settings → Hub background → Artwork style**.

## Design template

Every new card should define:

1. **Job:** the one action or outcome the app represents.
2. **Focal subject:** one dominant object, pose, or interaction.
3. **Supporting cue:** at most two secondary cues that clarify timing, measurement, or feedback.
4. **Crop plan:** the focal subject must survive a centered 16:9 crop and a centered circular crop.
5. **Palette:** Focus Mode uses ink navy, muted blue-green, warm sand, soft stone, and restrained clay. Professional uses a slate/charcoal foundation, muted teal structure, off-white detail, and one amber emphasis.
6. **Motion budget:** use a single directional cue; avoid multiple competing trails, targets, or glows.
7. **Accessibility:** no essential information lives only inside the image. App name, purpose, and action remain interface text.
8. **Trust:** avoid childish toy rendering, realistic internal anatomy, stereotypes, and unsupported medical outcomes.

## Pose-overlay standard

Artwork that shows a tracked person uses the same simplified topology as the application. Each person has exactly 12 bilateral landmarks: left/right shoulder, elbow, wrist, hip, knee, and ankle.

Connections are limited to:

- shoulder to shoulder and hip to hip;
- each shoulder to the hip on the same side;
- each shoulder → elbow → wrist chain; and
- each hip → knee → ankle chain.

A knee must never connect to a hip midpoint, torso midpoint, or the opposite hip. For artwork whose pose is difficult for image generation to resolve reliably, use `scripts/apply_pose_artwork_overlay.py` with a checked JSON coordinate specification in `assets/hub_card_specs`. This makes the final landmark graph deterministic instead of relying on approximate generated geometry.

## Review workflow

Run:

```powershell
python scripts/review_hub_artwork.py
```

The report checks filename parity, dimensions, saturation, and luminance range. A reviewer then evaluates the manual criteria printed after the automated report: hierarchy, crop safety, consistency, cognitive load, and semantic accuracy.

If a card fails, change one variable at a time—composition first, then palette, then lighting/detail—and rerun the report before replacing the asset.
