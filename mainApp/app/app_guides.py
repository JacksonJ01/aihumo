"""Structured, reusable help content for every Main Hub application."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppGuide:
    purpose: str
    before_you_start: tuple[str, ...]
    steps: tuple[str, ...]
    review: tuple[str, ...]
    safety: str = ""
    video_status: str = "Video guide coming soon."


APP_GUIDES: dict[str, AppGuide] = {
    "pipeline": AppGuide(
        "Process recordings, build pose features, label movement, align cameras, and inspect synchronized measurements.",
        ("Choose a recording or an existing AIHuMo workspace.", "Confirm the participant, session, and camera details."),
        ("Open the workflow you need from Data Studio.", "Process raw video in Mode 0, or open existing processed data.",
         "Annotate, align, or review graphs, then save before leaving the workspace."),
        ("Check warnings and missing-pose sections.", "Confirm saved files belong to the intended session and recording."),
    ),
    "just_dance": AppGuide(
        "Practice rhythm, coordination, and movement consistency with music-led prompts.",
        ("Clear enough space to move safely.", "Place the camera where your full body remains visible."),
        ("Choose the routine and difficulty.", "Complete the short movement-range check.",
         "Follow the timing and pose cues, then finish the round."),
        ("Review timing accuracy, movement consistency, and replay similarity.",),
        "Stop if the space becomes obstructed or movement feels unsafe.",
    ),
    "flow_zone": AppGuide(
        "React to target, escape, and avoidance zones while building agility and spatial control.",
        ("Clear the floor and keep the full play area in frame.", "Complete calibration so zones match your safe reach."),
        ("Choose the grid size and difficulty.", "Enter, leave, or avoid the highlighted zone as instructed.",
         "Return to a ready position between prompts."),
        ("Review reaction time, accuracy, overshoot, and time in the correct zone.",),
        "Use a difficulty that stays inside your comfortable movement range.",
    ),
    "mirror_match": AppGuide(
        "Copy a reference pose or movement and improve symmetry, stability, and synchronization.",
        ("Select a reference recording, live mirror, or partner mode.", "Stand where the camera can see the required joints."),
        ("Complete calibration.", "Match the displayed pose or movement.", "Hold steady until the prompt completes."),
        ("Review joint similarity, left-right symmetry, hold stability, and timing.",),
    ),
    "balance": AppGuide(
        "Practice controlled weight shifts and stable holds within a calibrated safe range.",
        ("Use a level, non-slip surface.", "Keep a stable support nearby if you may need it."),
        ("Calibrate your comfortable standing and reaching range.", "Follow the center-control or freeze-pose target.",
         "Return to a stable neutral position after each prompt."),
        ("Review sway, hold time, target accuracy, and recovery control.",),
        "Stop immediately if you feel pain, dizziness, or unsteadiness.",
    ),
    "path_precision": AppGuide(
        "Trace paths and reach targets with smooth, accurate, controlled movement.",
        ("Choose the hand, foot, or body point to track.", "Calibrate a comfortable reach area."),
        ("Choose a path or precision-target drill.", "Follow the route without rushing.",
         "Complete the path and return to the start marker."),
        ("Review path error, smoothness, speed, and overshoot.",),
    ),
    "sports": AppGuide(
        "Train sport-style reaction, reach, recovery, and directional control.",
        ("Clear the play area and choose a drill appropriate for the space.", "Complete the ready-stance calibration."),
        ("Start from the ready position.", "Respond to each directional or reach prompt.",
         "Recover to a controlled stance before the next prompt."),
        ("Review reaction time, reach accuracy, recovery time, and stance consistency.",),
        "Avoid drills that require more room or speed than the environment safely permits.",
    ),
    "rehab": AppGuide(
        "Review controlled range-of-motion and stability tasks using clinician-defined targets.",
        ("Use only tasks and limits approved for the participant.", "Position the camera to keep the measured area visible."),
        ("Select the assigned task and tolerance.", "Complete calibration without forcing the movement.",
         "Perform each repetition slowly and stop the session if needed."),
        ("Review range, control, stability, and changes between sessions.",),
        "This is an analysis aid, not medical advice. Stop for pain, dizziness, numbness, or unusual symptoms.",
    ),
    "ergonomics": AppGuide(
        "Review posture, lifting, reaching, bending, and repetitive movement patterns.",
        ("Choose a camera view that clearly shows the task.", "Keep the normal work area and equipment in frame."),
        ("Record or load the task.", "Perform the movement naturally.",
         "Review flagged positions, then repeat after making an adjustment."),
        ("Compare posture duration, repetition, reach, bending, and movement consistency.",),
        "Use the results as a review aid; qualified workplace or clinical guidance takes priority.",
    ),
    "gait": AppGuide(
        "Review walking symmetry, stride timing, transitions, turning, and stability.",
        ("Use an unobstructed walkway.", "Choose a front, side, or three-quarter camera view."),
        ("Complete the standing calibration.", "Walk and turn at a comfortable pace.",
         "Finish beyond the marked capture area before stopping."),
        ("Review cadence, stride consistency, left-right symmetry, turning, and stability.",),
        "This workspace supports observation and is not a diagnostic tool.",
    ),
    "sequence": AppGuide(
        "Combine memory, reaction, and body control by visiting zones in the displayed order.",
        ("Clear the floor and calibrate the playable zone.", "Choose the sequence length and difficulty."),
        ("Watch the full sequence.", "Move through the zones in the same order.", "Return to ready for the next round."),
        ("Review sequence accuracy, reaction time, movement control, and recall across rounds.",),
    ),
    "spelling_bee": AppGuide(
        "Practice vocabulary, spelling, definitions, and recall without requiring a camera.",
        ("Choose a dictionary level, difficulty, and number of rounds.",),
        ("Listen to or read the word prompt and definition.", "Enter or say the spelling.",
         "Submit the answer and continue through the round."),
        ("Review correct answers, difficult words, and accuracy by difficulty.",),
    ),
    "math_challenge": AppGuide(
        "Practice arithmetic accuracy and recall with scalable difficulty.",
        ("Choose operations, difficulty, and number of rounds.",),
        ("Read each problem.", "Enter the answer and submit it.", "Review the explanation before continuing when needed."),
        ("Review accuracy, response time, and performance by operation.",),
    ),
}


def guide_for(app_id: str) -> AppGuide | None:
    return APP_GUIDES.get(app_id)


def guides_markdown(apps) -> str:
    """Render guide content as a durable document using the current Hub ordering."""
    lines = ["# AIHuMo application guides", "", "Purpose and operating steps for every application in the Main Hub.", ""]
    for app in apps:
        guide = guide_for(app.id)
        if guide is None:
            continue
        lines.extend((f"## {app.title}", "", guide.purpose, "", "### Before you start", ""))
        lines.extend(f"- {item}" for item in guide.before_you_start)
        lines.extend(("", "### How to use", ""))
        lines.extend(f"{index}. {item}" for index, item in enumerate(guide.steps, 1))
        lines.extend(("", "### Review", ""))
        lines.extend(f"- {item}" for item in guide.review)
        if guide.safety:
            lines.extend(("", "### Safety and notes", "", guide.safety))
        lines.extend(("", f"> {guide.video_status}", ""))
    return "\n".join(lines).rstrip() + "\n"
