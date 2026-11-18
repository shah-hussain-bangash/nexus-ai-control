# UI acceptance checklist — 0.9.0

## Verified in this release

- [x] All 18 modules render their dedicated operational views with synthetic records.
- [x] Domain form defaults and state-machine definitions pass automated validation.
- [x] Operational records/events persist in real backend revisions across all 18 modules.
- [x] Invalid/forged transitions and failed scenarios cannot advance record state.
- [x] Agent queue/start/uncertain-pause path and UI revision save checked in the browser.
- [x] Dirty parent plan blocks global dashboard navigation; keep/discard paths checked.
- [x] File chooser metadata intake and synthetic citation search checked.
- [x] Unavailable/retry review checked; no document overflow at 1363px desktop width.
- [x] Operational record titles use bright text and 15px in larger-text mode.

## Still required for deployment acceptance

- [ ] Real Windows installation and representative customer data.
- [ ] Mobile and tablet devices, Safari/Firefox/Edge and touch interaction.
- [ ] Actual screen readers, zoom/reflow, reduced motion and complete keyboard journeys.
- [ ] Every runtime-connected loading/error/timeout/retry state against real adapters.
- [ ] Independent contrast/accessibility, security, performance and recovery assessments.
- [ ] Comprehensive dirty-state guard for all legacy forms.

No automatic UI checklist is a certification. Record environment-specific findings and evidence before release approval.

## Added function design scope

- [x] All 216 screen definitions and 648 function controls validate in automated tests.
- [x] Real revision persistence and UI review gating tested across all 18 modules.
- [x] Browser search/open/edit/review/save/filter/export journey verified for selected functions.
- [x] UI previews preserve the distinction between planned contracts and active runtime services.
- [ ] Formal review of every function against actual customer requirements and real data.
- [ ] Browser/device and assistive-technology acceptance for every production-critical journey.
