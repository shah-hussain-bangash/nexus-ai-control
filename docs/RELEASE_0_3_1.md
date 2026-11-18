# NEXUS AI Control 0.3.1 - luminous interface

This visual release follows the uploaded Agentic AI Architecture reference: deep navy/cobalt surfaces, cyan and violet edges, a white/blue 3D AI robot, holographic platform, glass panels and seven colored capability tiles. NEXUS branding and the full enterprise platform title are retained. Website headings, form labels, workflow labels, navigation and tile captions are HTML text, not baked into the image.

## Changes

- Shared dark visual theme in `frontend/src/neon.css` for sign-in, dashboard, navigation, registries, tables, settings, readiness and dialogs.
- Complete robot illustration in `frontend/public/nexus-agent-neon.png`; identical asset included with the standalone demo.
- Sign-in feature rail and linked dashboard shortcuts for existing platform views.
- Dashboard artwork/hero, clear white/cyan typography, darker input surfaces and visible focus treatment.
- Existing local/organization sign-in and role-based controls retained. Hash navigation scrolls to the top.
- Responsive layouts and reduced-motion rules supplied. Desktop visual review does not certify every mobile device or accessibility criterion.

## Scope and verification

This release changes presentation and version metadata; it does not implement the enterprise integrations remaining in the 0.3.0 implementation report. The server-backed application is in frontend/ and backend/. The hosted Site and demo-preview/ are synthetic read-only UI demonstrations with simulated sign-in.

The complete 97-test PostgreSQL/OPA/Keycloak run and 85-pass SQLite regression were completed for the 0.3.0 functional baseline and retained as historical evidence. The visual patch is checked through TypeScript/Vite builds, desktop browser inspection and a clean packaged application workflow smoke check; those baseline suites are not claimed as newly rerun for this styling patch.

No schema change: preserve .env and both databases, follow docs/UPGRADE_0_3_0.md, and replace/rebuild the frontend assets. Health reports release 0.3.1; schema stays at 2.

## Artwork provenance

The built-in image generation tool produced the project artwork from the uploaded image as a style/subject reference. The original upload was not modified. Project asset: frontend/public/nexus-agent-neon.png.

Prompt: Use the supplied image as a style and subject reference for a production website illustration. Create a premium 3D hero artwork for NEXUS AI Control: the same delightful glossy white and electric-blue AI robot with black glass face and cyan eyes hovering above a luminous cyan holographic platform, in a deep navy server room. A transparent cyan glass panel with subtle abstract node lines is behind the robot on the right; do not put any text, letters, logos, icons, numbers or words anywhere. Retain the reference's polished vibrant cyan, cobalt blue and violet lighting, holographic reflections and delicate connected network floor. Landscape 3:2 composition. Robot large, centered, entire body visible. Dark navy edges that blend naturally into a #05152f webpage. No image borders. This is an illustration asset only, not a full website mockup; all website text will be typeset separately for perfect legibility.
