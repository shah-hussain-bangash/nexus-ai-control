# Disposable Docker recovery from a clean checkout

This opt-in rehearsal builds its own candidate image from the exact Git commit, creates fresh synthetic SQLite databases and credentials in memory, makes and inspects an encrypted backup, restores it to a separate directory, then exercises that copy through a local Docker API and fixed-target gateway. No existing account password, backup, database path, runtime `.env`, cloud target or published image is an input. The normal app can remain open.

Use a clean Git checkout with Docker Desktop in Linux-container mode, or a Linux Docker engine with Compose v2-compatible commands. The selected Docker context must use a local named pipe or Unix socket; TCP/SSH contexts are refused. Backend development dependencies must be installed in the Python environment invoking the tool. The image build may download base images and declared dependencies.

On Unix, use a non-root host account with Docker access. The containers run as that account's UID/GID so native recovery's private `0700` directories and `0600` files stay protected without changing their modes. Root Unix invocation is refused. Windows uses the tested non-root container user `10001:10001`; actual Docker Desktop mount behavior is checked by the runtime exercise.

For a fresh Windows checkout, create a Python environment and install dependencies without initializing an application database:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd run check:docker-recovery
npm.cmd run test:docker-recovery
```

The first check inspects source/CLI prerequisites only. It does not contact the Docker engine, validate mount permissions, build images or establish recovery acceptance. The second command explicitly opts into the disposable Docker exercise. Portable equivalents:

```sh
python scripts/run_docker_recovery_drill.py --check
python scripts/run_docker_recovery_drill.py --run
```

No password prompt is needed: a new fixture password and test runtime secrets remain in process for this invocation. Three demo accounts belong only to the synthetic source and restored copy. Reports contain fixed checks/statuses and source/image metadata, never the password, session cookies, runtime keys, record contents or raw tool exceptions. Docker itself holds the test runtime environment while its containers exist. Its ordinary local client configuration may be used for context selection/base-image access; it is not dumped or included in the source archive.

The build context comes from `git archive`, excluding ignored/untracked operator files. Modified or untracked source files are refused; ignored local state is preserved. Source symlinks/submodules and unsafe export paths are refused. A unique build tag/run label identifies this invocation's image. Base-image tags in the existing Dockerfile remain mutable, so this is a recorded candidate build rather than a bit-for-bit reproducibility or security claim.

After fixture writers close, native encrypted backup/inspection and the existing isolated SQLite-copy primitive must pass. All logical control/business rows match before opening the recovered in-process probe. That probe and the later container never migrate or seed the recovered database. The file-copy primitive still does not claim it started an application.

The Docker stage verifies readiness/schema, anonymous and CSRF rejection, fresh fixture login, the known prompt/configuration, auditor reads and valid-context write rejection, an owner write, record persistence across restart and auditor rejection again. It checks actual port bindings and unchanged original fixture/encrypted input. An automatically selected unused localhost port avoids a fixed port shared with the active app; a concurrent bind conflict fails instead of replacing a listener.

The API attaches only to an internal recovery network. A second container runs the small bounded TCP gateway from the same built image and forwards only to `recovered-api:8000`. The gateway has no database mount or NEXUS runtime keys. It alone publishes on `127.0.0.1` and has the access-network attachment required for Docker host publishing. It is not a general URL-selected proxy. Explicit empty proxy variables avoid inheriting proxy settings in these test services. This topology is a local synthetic test boundary, not production egress-control acceptance.

Finally, the runtime verifies ownership labels and removes only its generated project containers/networks. The driver removes only its own newly generated image tag and its marked temporary directory after container cleanup is confirmed. It never prunes Docker globally or removes existing volumes/images. If build outcome or runtime cleanup is uncertain, it retains the owned workspace/image and reports failure; it does not delete a potentially active mount. Retained files are synthetic and remain for protected local review. Cleanup is not secure erasure.

A unique unsigned JSON receipt is published under ignored `backend/data/drills`. `--output-dir` may select a directory outside the checkout or under that ignored report directory. A receipt passes only if runtime acceptance, source preservation and owned cleanup all pass. Build, fixture and runtime results remain separate; their checks overlap and must not be summed as unique aggregate coverage. A local image reference is recorded as Docker reports it, without assuming its registry descriptor type.

The path-filtered `Disposable Docker recovery` pull-request workflow runs this exact command from a fresh checkout with read-only repository permissions and no persisted checkout credential. It uploads only the summary receipt. Regular safety/fixture/gateway unit tests run in the existing backend jobs; mocked orchestration tests are not Docker restore evidence. The new workflow is limited to changes in the tool/test/workflow paths. It does not add Docker recovery to the existing eight-drill synthetic suite or make every unrelated PR build a new image.

This exercise does not establish customer/pilot identity, MFA/OPA/TLS, PostgreSQL deployment recovery, production cutover/rollback, scheduled/off-host backups, real key custody, power-loss durability, authenticated independent evidence or measured production RPO/RTO. The archive key is ephemeral and not retained. Hard interruption or runner termination can prevent complete cleanup or receipt publication; absence of a passing receipt grants no acceptance. The production recovery roadmap remains partial.
