# AIHuMo native desktop builds

This directory contains reproducible builds for Windows x64, Linux x64,
macOS Intel x64, and macOS Apple Silicon arm64. User recordings, annotations,
checkpoints, test artifacts, and local settings are intentionally excluded.

## Windows build

From PowerShell in this directory:

```powershell
.\Windows\build_installer.ps1 -Version 0.5.0
```

The script uses `..\.venv` by default. Pass `-PythonExe` to use a separate build
environment. Install PyInstaller in that environment and place the MediaPipe
pose model at `..\full_model\pose_landmarker_full.task` before building.
The executable and runtime files are under `dist\v<version>\`. The script
creates a portable ZIP, a guided Setup EXE, and SHA-256 checksums under
`release\`. Inno Setup 6 is required for the Setup EXE. Build outputs are
versioned, and the scripts refuse to overwrite an existing version.

The installer asks for install permissions, participant/camera defaults,
default data folders, and an optional starter recording bundle. It writes a
small bootstrap plan to the user's local application-data folder. AIHuMo
reviews that plan on first launch and does not copy, move, delete, or upload
the selected recordings.

## Linux and macOS builds

Each Unix platform has its own native script and README:

- `Linux/build_portable.sh`
- `macOS/build_portable.sh`

PyInstaller packages must be built on the operating system they target. macOS
builds produce ZIP and DMG files; Linux builds produce tar.gz and DEB files. The
GitHub Actions workflow `.github/workflows/desktop-cross-platform.yml` runs all
four native builds. Pushing a tag such as `desktop-v0.5.0` validates the version,
builds and smoke-tests every package, creates the matching GitHub Release, and
uploads each package with its SHA-256 checksum.

## Included runtime assets

- Desktop application and `aihumo` pipeline modules
- PyQt6, OpenCV, pandas, PyArrow, Matplotlib, and MediaPipe runtime dependencies
- `configs\config.json`
- `full_model\pose_landmarker_full.task`
- Frozen-safe dispatch for the Prepare Existing Recording utility

## Later production work

Public releases still need platform code signing/notarization, automatic
upgrades, crash logs, and a complete license/third-party notice bundle.
