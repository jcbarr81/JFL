# Windows Packaging

The Windows launcher bundles the API simulation stack and the PyQt play editor into a single executable. PyInstaller uses packaging/gridironsim.spec to assemble the build and copy default assets.

## Prerequisites

- Windows 11 host
- Python 3.11 (same version used for development)
- Virtual environment with project requirements installed (pip install -r requirements.txt)
- PyInstaller 6.x (pip install pyinstaller)

## Build steps

`powershell
# From the project root
pyinstaller packaging/gridironsim.spec --noconfirm
`

PyInstaller emits the launcher under dist/GridironSim/GridironSim.exe. Copy the entire dist/GridironSim/ directory when distributing—the .exe expects the adjacent libraries and ssets/ folder that contains the bundled database and sample plays.

## Runtime behavior

- On first launch the executable copies gridiron.db and every sample play from the embedded ssets/ directory into %LOCALAPPDATA%\GridironSim. Existing user-modified files are left untouched (the copy happens only when a file is missing).
- The working directory is set to %LOCALAPPDATA%\GridironSim. All exports (for example uild/season/*.csv) and savepoints live under this folder, keeping user data separate from the install location.
- Two primary actions are available:
  - **Run Season Simulation** – executes scripts.run_season.run_season() on a background thread with a random seed. Results and the export folder path appear in the launcher log.
  - **Open Play Editor** – opens the PyQt play editor window against the user data copy of data/plays/.
- Use **Open Data Directory** to reveal the %LOCALAPPDATA%\GridironSim folder for manual inspection or backup.

## Updating bundled assets

If new default plays or database templates are added, re-run PyInstaller so the ssets/ folder in the distribution matches the repository state. The launcher only copies files that do not yet exist in %LOCALAPPDATA%\GridironSim, so existing installs keep user modifications while still acquiring new defaults on future builds.

## Verifying the build

1. Double-click GridironSim.exe to open the launcher.
2. Run a season; confirm the status updates and that CSV/JSON exports appear under %LOCALAPPDATA%\GridironSim\build\season.
3. Open the play editor; load and edit plays from %LOCALAPPDATA%\GridironSim\data\plays.
4. Delete %LOCALAPPDATA%\GridironSim to test first-run provisioning.
