# Project conventions
- Use Python standard library plus plain HTML/CSS/JS unless a concrete need justifies dependencies.
- Keep runtime data, credentials, media and private project material out of Git.
- All starter content is demonstration planning data. Never fabricate generation, provider connectivity, cost or quality approval.
- Human storyboard approval must precede generation. Unknown submissions must never auto-retry. Persist provider ids and reservations.
- Test budget, approval, duplicate and timeout behavior when execution code changes.
- Keep the server bound to loopback. External providers and paid workflows require separate explicit authorization and a reviewed adapter.
- The user authorizes normal iteration releases to daijizai/video-agent-studio after relevant tests and secret scans pass, without asking again. This does not authorize paid generation, secret disclosure, or destructive remote-history rewrites.
- Keep preview screenshots local: public screenshot upload was rejected by automatic approval review. Publish source/text documentation only unless separate image publication authorization is established.

- Honor the project's generation pause across image, video and local workflow submissions. Budget/model edits do not resume execution; retain unused balances and evidence.
- Derive stages through workflow_state.py from persisted facts. Current image approvals are content/image-bound; provisional film acceptance is distinct from objective quality guarantees.

## Creative workflows
- Read `skills/frame-screenplay/SKILL.md` for scripts/shots, `skills/frame-character-assets/SKILL.md` for character designs/views, and `skills/frame-object-assets/SKILL.md` for object designs/views. Load only relevant templates.
- For character standard-view plans, also read `skills/frame-character-assets/templates/six-views.md`: plan head and full-body front/side/back as separate images, while preserving the user's approval and budget gates.
- For project-wide visual style and reference-image design, read `skills/frame-visual-style/SKILL.md`; preserve the detailed style bible and record the model-specific request without silently truncating it.
- Keep reusable creative methods in these versioned Skills. Codex applies them to project material; Python/JS enforces data and execution contracts. Do not move budget, approval, credential or path enforcement out of code.
- Ordinary UI shows stories, designs, media, versions, costs and feedback. Machine prompts and consistency records remain backstage; hiding them must not delete history or silently change requests.
