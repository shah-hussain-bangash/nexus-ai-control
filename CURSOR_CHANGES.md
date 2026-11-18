# Cursor Windows package changes

Based on the supplied NEXUS AI Control 0.16.0 archive. Application behavior and
the upstream feature scope remain as described in the original documentation.

- Added `scripts/cursor.ps1` and root setup/start/build/test commands.
- Preserved the local launcher's automatic fallback when port 8000 is occupied;
  explicit `-Port` values still request a fixed port (or an available port for 0).
- Added Cursor-compatible `.vscode` tasks, interpreter settings and debugging.
- Added `CURSOR_QUICKSTART.md` with installation, login and password recovery steps.
- Renamed `ProductExperience.tsx` to `ProductExperienceView.tsx` in both frontends
  and updated imports and the source packaging requirement. On Windows,
  TypeScript resolved the extensionless component import to `productExperience.ts`
  and failed with case-collision and missing-export errors.
- Used Vite's runner configuration loader for builds, which also passed in the
  restricted verification environment where the default configuration bundler
  tried to read a parent directory outside the project.
- Rebuilt both frontend distributions from the edited source.
- Fixed the POSIX-only hybrid worker test to skip on Windows before accessing
  `os.killpg`, which is unavailable there. Its previous platform guard ran too late.

Original release test reports under `docs` are historical upstream evidence.
Current package verification is recorded separately in `CURSOR_VERIFICATION.json`.
The source manifest is refreshed when this Cursor ZIP is packaged.

No generated accounts, private configuration, databases, dependencies or virtual
environment are included in the ZIP. Setup creates these on your computer.
