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
- For character standard-view plans, also read `skills/frame-character-assets/templates/six-views.md`: prioritize full-body front/side/back; derive head crops where adequate and plan extra head images only when needed, preserving approval and budget gates.
- For project-wide visual style and reference-image design, read `skills/frame-visual-style/SKILL.md`; preserve the detailed style bible and record the model-specific request without silently truncating it.
- Keep reusable creative methods in these versioned Skills. Codex applies them to project material; Python/JS enforces data and execution contracts. Do not move budget, approval, credential or path enforcement out of code.
- Ordinary UI shows stories, designs, media, versions, costs and feedback. Machine prompts and consistency records remain backstage; hiding them must not delete history or silently change requests.

- For material-reference video shot prompts without prerequisite keyframes, read `skills/frame-video-prompts/SKILL.md`. Keep material and shot approval bound; do not silently reuse storyboard images as first frames.
- For reusable scene designs and environment reference images, read `skills/frame-scene-assets/SKILL.md`. A scene reference is not automatically a first frame or an approved image.
- For reusable relative-size reference images, read `skills/frame-scale-reference/SKILL.md`. Keep referenced character versions explicit and do not treat the image as an implicit first frame.
- For every scene containing two or more visible objects or subjects, prepare a same-frame relative-size reference and obtain the user's explicit approval before generating that scene's video. Include characters, animals, vehicles, props, and other visible objects; do not infer true size from image pixels or substitute identity images for scale. Reuse an existing scale reference only after the user explicitly confirms it covers the scene's objects and their relative sizes. A proposed proportion is not an approval, and broad budget or generation authorization does not replace this scene-specific confirmation.

- 禁止跨项目绑定或迁移素材、采用版本或参考图；每个项目只使用本项目内独立准备并确认的素材。即便其他项目已有同一角色，也不得复制、导入、继承或绑定其资产或采用记录。

- 新生成并归档的片段自动进入视频总览和剪辑预览（标明待审阅），不自动标记验收；新增片段时保留已有剪辑范围。

- 项目首页封面使用从成片中挑选的清晰关键帧，优先展示角色和故事重点，不默认使用首帧；保存来源视频、时间和图片，并在首页核验。
