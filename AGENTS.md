# Codex guidance for simple_sumo_web_local

## Goal
Improve the visual quality and usability of the existing React + Vite + TypeScript scientific simulation platform without changing business behavior.

## Skills
For frontend redesign, read and apply `.agents/skills/frontend-design/SKILL.md`. Treat it as design guidance, not permission to change application behavior.

## Boundaries
- Prefer edits under `frontend/src/components/`, `frontend/src/style.css`, and other presentation-only frontend files.
- Preserve API endpoints/contracts, React state semantics, route/navigation behavior, input provenance, real-time and historical data integration, SUMO/ASM simulation, model parameters, and Plotly data/handlers.
- Do not modify `backend/`, `private/`, Docker/production configuration, credentials, or data files for UI redesign.
- Do not introduce new UI libraries unless justified and explicitly approved.
- Keep existing Chinese/English translations, labels, numerical precision, and units correct.
- Do not push or merge to `main`.

## Workflow
1. Inspect the repo, current design system, and critical user workflows.
2. Propose a brief staged redesign plan with visual direction; do not edit app source until asked.
3. Make small, reviewable visual changes and explain affected components.
4. Run `npm run build` within `frontend/`, and existing relevant tests if available.
5. Use screenshots/browser inspection when available. Check responsive layout, keyboard focus, contrast, overflow, and Plotly interactions.
6. Report exact files changed, test results, and any unverified flows; never claim full functional preservation without testing.
