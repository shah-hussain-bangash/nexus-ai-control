# Upgrade to 0.12.0

1. Stop every API and execution worker with Ctrl+C. Back up the existing source, private .env, application/business databases and retained data. Verify the backup before copying updates.
2. Extract the new ZIP into a review directory. Copy new source into C:\nexus-ai-control while preserving private .env, data/ and backups/. Never replace private settings with .env.example or delete a database to resolve an upgrade issue.
3. Start:

```powershell
cd C:\nexus-ai-control
.\scripts\start.cmd
```

Schema stays 7. Existing accounts, documents, workflows, decisions and keys are preserved. Prior schema versions are migrated forward by the starter as before. Existing workflows that predate destination binding remain bound to the original synthetic destination. No HTTP adapter is enabled automatically.

4. Open the new printed URL, keep the terminal open and hard-refresh old assets. The light workspace is the new default; use the appearance button to retain a dark theme. Saved large-text preference still works.
5. Open Release readiness → Runtime signals. Synthetic mode should remain selected unless an operator explicitly configured the HTTPS adapter. Follow BUSINESS_CONNECTOR_0_12_0.md in an approved customer sandbox before enabling external effects.
6. For encrypted backups, provision the key through a protected secret store and follow OPERATIONS_0_12_0.md after stopping writers. An existing plaintext backup is not automatically encrypted by upgrading.

Rollback: stop processes and restore matching previous source/settings plus its verified backup. Review queued actions and adapter bindings before running older workers. Never switch adapter destinations to force an old approval to execute elsewhere. Native Windows/cloud rollout and restore acceptance remain deployment responsibilities.
