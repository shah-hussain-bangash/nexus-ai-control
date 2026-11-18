# Source code on GitHub

Repository: https://github.com/zenithdevelopers7-source/nexus-ai-control

Open this project folder in Cursor. In a separate terminal from the running app:

```powershell
npm.cmd run sync:auto
```

If Git asks you to sign in, complete GitHub sign-in in your own browser. Keep this
terminal open. Saved file changes are committed and pushed after 5 quiet seconds.
Ctrl+C stops auto-sync. Run it again when you reopen Cursor. Unsaved edits remain
in the editor until you save. Keep this one working folder for future edits.

To upload once instead:

```powershell
npm.cmd run sync
```

The `.gitignore` excludes local secrets, account databases, virtual environments,
dependencies, private keys, backups and generated frontend builds. Keep provider
keys and passwords in `backend/.env`, never in source files. Your account records
stay local; cloning the repository creates a separate local workspace after setup.

Sync records and uploads all eligible saved changes, including deletions. It does
not run a build or tests before each upload. Run `npm.cmd run build` and
`npm.cmd test` when needed. If another computer changes the repository, a rejected
push stops sync so you can resolve the incoming changes in Cursor; it never force
pushes or silently overwrites remote changes.

Source uploads do not deploy a hosted application. Running the app still uses the
local setup and start commands in `CURSOR_QUICKSTART.md`.
