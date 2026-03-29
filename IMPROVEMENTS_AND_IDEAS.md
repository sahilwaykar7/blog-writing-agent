# Blog Writing Agent – Improvements & New Ideas

A review of your codebase with concrete improvements and feature ideas.

---

## Part 1: Where to Improve

### 1. Code quality & robustness

| Area | Current | Improvement |
|------|---------|-------------|
| **Logging** | No structured logging; only frontend "event log" and bare `except` in places | Add `logging` in backend: log router decision, research hits, plan, worker sections, image success/fail. Use `logger.exception` in `except` blocks instead of swallowing errors. |
| **Tavily errors** | `_tavily_search` catches all exceptions and returns `[]` silently | At least log the exception; optionally surface "Research unavailable" in state/UI when `TAVILY_API_KEY` is missing or Tavily fails. |
| **Stream fallback** | `try_stream` swallows exceptions and falls back to invoke | Log which mode (stream vs invoke) is used; on final failure show a clear error in the UI instead of generic traceback. |
| **LLM config** | Model and temperature hardcoded (`gpt-4.1-mini`) | Read from env (e.g. `OPENAI_MODEL`, `OPENAI_TEMPERATURE`) so you can switch models or tune without code change. |
| **Duplicate helpers** | `safe_slug` in both `bwa_backend` and `bwa_frontend` | Move to a small shared module (e.g. `utils.py`) and import in both. |
| **Image output dir** | All blogs share one `images/` folder; filenames can collide across runs | Save per-blog: e.g. `output/<slug>/` with `output/<slug>/blog.md` and `output/<slug>/images/`. Optionally make output base dir configurable via env. |
| **API retries** | No retries on OpenAI/Gemini/Tavily | Add retries with backoff for 429/5xx in image generation and (if you use a client) for LLM calls so transient failures don’t fail the whole run. |

### 2. Backend (LangGraph) improvements

- **Checkpointing**: Enable LangGraph checkpointer so runs can be resumed after a crash or so you can inspect state at each step.
- **Human-in-the-loop**: After the orchestrator, add an optional "approve plan" step (e.g. in UI: show plan → user clicks "Continue" or edits tasks) before fanout to workers.
- **Worker failure**: If one worker fails, the whole graph fails. Consider per-section try/except and storing failed section IDs so the rest of the blog still completes and you can retry only failed sections.
- **Router reason**: You have `RouterDecision.reason` but don’t pass it to state/UI; exposing it in the Plan tab would help users understand why research was or wasn’t used.
- **Token/cost visibility**: Optional: log or display approximate token usage (and cost) per run (router, research, orchestrator, workers, images) for budgeting and debugging.

### 3. Frontend (Streamlit) improvements

- **Progress**: Show a clear step-by-step progress (e.g. "Router → Research → Plan → Writing sections (3/7) → Images") instead of only raw node names and JSON.
- **Topic prefill**: When user loads a past blog, prefill the topic input with the blog title so they can regenerate or tweak easily.
- **Error display**: If the graph invocation fails, show a clear message (e.g. "Generation failed: …") in a dedicated area instead of only in logs.
- **Images tab**: When images are generated, show which provider was used (OpenAI vs Gemini) if you track it in state.
- **Past blogs**: Exclude `README.md` from "Past blogs" (or any file named `README.md`) so it doesn’t appear as a generated blog.
- **Output directory**: If you add configurable output dir, add a setting in the sidebar (or env) and show "Saved to: …" after a successful run.

### 4. Security & configuration

- **Secrets**: Ensure `.env` is never committed (you have `.gitignore`; keep it). Don’t log or display API keys.
- **Config file**: Optional `config.yaml` or env for: default model, output dir, max images, max worker retries, so non-devs can tune without editing code.

### 5. Testing & maintainability

- **Tests**: Add a minimal test suite: e.g. `_safe_slug`, router/orchestrator with mocked LLM, and a single end-to-end test with mocks for OpenAI/Tavily/Gemini so refactors don’t break the pipeline.
- **Type hints**: You already use TypedDict and Pydantic; keep using them for new state and payloads so the graph stays clear and IDE-friendly.
- **Docs**: Keep README up to date; add a short "Architecture" section (router → research → orchestrator → workers → reducer/images) and document env vars in one place.

---

## Part 2: New Ideas for the Agent & Blog Creation

### Content & planning

1. **Tone / style presets**  
   Let the user pick a preset (e.g. "Formal", "Casual", "Developer advocate", "Academic") and pass it into the orchestrator so tone is consistent and controllable.

2. **Outline editing before writing**  
   After the plan is generated, show the outline (tasks + bullets) in an editable form; user can add/remove/reorder tasks or edit bullets, then click "Write" to run only the workers (and downstream). Requires storing plan in state and optionally a "plan-only" run mode.

3. **Target length control**  
   Add a "Short / Medium / Long" or a word-range selector (e.g. 800–1200 words) and map it to `target_words` so the orchestrator and workers get a single consistent constraint.

4. **SEO / meta**  
   Add a node (or extend the orchestrator) to output meta title, meta description, and 3–5 suggested tags; render them in the Markdown Preview or in a separate "SEO" tab and optionally write them to frontmatter in the saved `.md`.

5. **Multi-language**  
   Add an option "Target language" (e.g. English, Spanish). Pass it into the orchestrator and workers so the whole blog is generated in that language (and research/evidence can stay in original with a note).

### Research & citations

6. **Citation style**  
   Support a chosen citation style (e.g. inline links vs numbered refs vs "Sources" section at the end) and instruct the worker and reducer to format accordingly.

7. **More research backends**  
   Besides Tavily, add optional SerpAPI, Brave Search, or a custom docs crawler so users can plug in their own doc set (e.g. internal wiki) and the agent grounds from that.

8. **Evidence quality filter**  
   Add a small step after research that scores or filters evidence (e.g. by domain, date, snippet relevance) and drops low-quality items before the orchestrator.

### Images & media

9. **Image style consistency**  
   Pass a global "image style" (e.g. "technical diagram", "minimal", "hand-drawn") into the image planner and into each image prompt so all figures look coherent.

10. **Optional image step**  
    Add a toggle "Include AI images" so users can run the full pipeline without the image step (plan + merge only) for faster runs or when they’ll add images manually.

11. **Placeholder images**  
    When image generation fails, instead of only a text block, optionally insert a placeholder image (e.g. a simple "Image: <caption>" graphic or a link to a stock-image search) so the layout stays consistent.

### UX & workflow

12. **Draft and publish**  
    Save runs as "drafts" (e.g. under `output/<slug>/` with metadata.json). Add "Publish" to copy or export to a CMS path, or trigger a Hugo/Jekyll build.

13. **Regenerate one section**  
    Let the user select a section (by task id or title) and "Regenerate this section" so only that worker runs again and the rest of the blog is unchanged. Requires storing plan + evidence in the draft and a small subgraph or single-worker invocation.

14. **Templates**  
    Allow "Blog from template": user picks a template (e.g. "Tutorial", "Comparison", "News roundup") that pre-fills blog_kind, tone, and maybe a fixed task structure; the orchestrator then only fills in topic-specific content.

15. **Slack / Discord / Email**  
    Optional step at the end: "Notify me when done" (webhook or email). Useful for long-running jobs.

### Technical & scale

16. **Async workers**  
    Run worker nodes in parallel (LangGraph supports this) so all sections are generated concurrently and total time drops.

17. **Caching**  
    Cache router + research + orchestrator output by (topic, as_of, mode) so repeated runs with the same topic reuse plan and evidence and only re-run workers/reducer (e.g. after user edits the outline).

18. **API mode**  
    Expose the compiled graph as a REST or LangServe API so the Streamlit app is one client; other clients (CLI, Slack bot, CMS) can trigger the same pipeline.

19. **Streaming sections**  
    Stream each section markdown to the UI as it’s ready (you already stream graph updates; ensure section content is pushed as soon as each worker finishes) so the user sees content appearing in real time.

20. **Cost and usage dashboard**  
    Optional tab or export: total tokens per run, cost estimate by provider (OpenAI text, OpenAI image, Gemini, Tavily), and simple usage over time for budgeting.

---

## Part 3: Quick wins (low effort, high impact)

1. **Exclude README from past blogs** in the frontend.
2. **Read LLM model from env** (e.g. `OPENAI_MODEL=gpt-4.1-mini`).
3. **Log and optionally show router `reason`** in the Plan tab.
4. **Add retries with backoff** for image generation (and optionally LLM) calls.
5. **Per-blog output directory** (`output/<slug>/`) to avoid image filename clashes and keep runs organized.
6. **"Include AI images" toggle** in the sidebar to skip the image step when not needed.

If you tell me which items you want to implement first (e.g. "quick wins" or "outline editing"), I can outline or write the exact code changes next.
