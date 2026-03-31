# Blog Writing Agent — Architecture

This document describes how the **blog-writing-agent** project is structured: components, data flow, LangGraph nodes, task model, and external integrations. It complements `README.md` (setup and usage).

---

## 1. High-level overview

The system is a **multi-stage LLM pipeline** built with **LangGraph**, exposed through a **Streamlit** UI. Optional steps add **web research (Tavily)**, **AI-generated images (OpenAI / Gemini fallback)**, and **publishing (Dev.to / Medium)** with **Cloudinary** for public image URLs.

```mermaid
flowchart TB
    subgraph ui [Streamlit UI]
        FE[bwa_frontend.py]
    end

    subgraph graph [LangGraph — bwa_backend.py]
        R[router]
        RS[research]
        O[orchestrator]
        W[worker x N]
        RED[reducer subgraph]
        R --> RS
        R --> O
        RS --> O
        O --> W
        W --> RED
    end

    subgraph red [Reducer subgraph]
        M[merge_content]
        D[decide_images]
        G[generate_and_place_images]
        M --> D --> G
    end

    FE --> graph
    TAVILY[(Tavily API)]
    OAI[(OpenAI API)]
    GEM[(Google Gemini)]
    RS -.-> TAVILY
    W --> OAI
    D --> OAI
    G --> OAI
    G -.-> GEM

    subgraph pub [Optional publish]
        P[publish.py]
        C[Cloudinary]
        DEV[Dev.to API]
        MED[Medium API]
    end

    FE --> P
    P --> C
    P --> DEV
    P --> MED
```

**Artifacts on disk**

- Final markdown: `{slug_from_blog_title}.md` in the project root.
- Images: `images/` when the image pipeline produces files.
- The Streamlit app also lists past `*.md` files in the current working directory.

---

## 2. Main modules

| Module | Role |
|--------|------|
| `bwa_backend.py` | Defines **state**, **Pydantic schemas**, **LangGraph** (`app`), and the compiled reducer subgraph. This is the canonical pipeline used by the UI. |
| `bwa_frontend.py` | **Streamlit** app: topic input, graph streaming, tabs (Plan, Evidence, Preview, Images, Logs), downloads, optional publish. |
| `publish.py` | **Dev.to** and **Medium** HTTP APIs; **Cloudinary** upload and markdown rewrite for local `images/` paths. |
| `1_bwa_basic.ipynb` … `5_bwa_image.ipynb` | Incremental **experiments** (basic graph → prompting → research → fine-tuning → images). Not required at runtime. |

The UI imports `from bwa_backend import app` — **not** the minimal notebook graph.

---

## 3. State model (`State` in `bwa_backend.py`)

The graph carries a single `TypedDict` state. Keys evolve as nodes run.

| Key | Purpose |
|-----|---------|
| `topic` | User’s blog topic (string). |
| `mode` | After **router**: `closed_book` \| `hybrid` \| `open_book`. |
| `needs_research` | Whether Tavily-backed research runs. |
| `queries` | Search queries from the router (when research is needed). |
| `evidence` | List of `EvidenceItem` (URLs, titles, snippets, dates). |
| `plan` | `Plan` object: title, audience, tone, `blog_kind`, `tasks[]`. |
| `as_of` | ISO date string (from UI “As-of date”). |
| `recency_days` | Window for filtering evidence (depends on `mode`). |
| `sections` | **Reducer list**: `Annotated[List[tuple[int, str]], operator.add]` — `(task_id, markdown)` pairs merged in order. |
| `merged_md` | Full post after **merge_content** (title + ordered sections). |
| `md_with_placeholders` | Markdown with `[[IMAGE_n]]` placeholders after **decide_images**. |
| `image_specs` | Serialized `ImageSpec` dicts for generation. |
| `final` | Final markdown string (placeholders replaced or failed blocks); also written to a `.md` file. |

**Fan-out behavior:** Multiple **worker** invocations append to `sections` via `operator.add`; **merge_content** sorts by `task.id` so section order matches the plan.

---

## 4. End-to-end execution order

1. **START → router**  
   Structured LLM output: `RouterDecision` (`needs_research`, `mode`, `queries`, `max_results_per_query`).  
   Sets `recency_days`: **7** (`open_book`), **45** (`hybrid`), **3650** (`closed_book`).

2. **Conditional: router → research OR orchestrator**  
   - If `needs_research` → **research**  
   - Else → **orchestrator** (skip research)

3. **research** (when selected)  
   - Runs Tavily per query (if `TAVILY_API_KEY` is set).  
   - LLM synthesizes `EvidencePack`; dedupes by URL.  
   - For `open_book`, filters evidence by `as_of` − `recency_days`.

4. **orchestrator**  
   Produces `Plan`: `blog_title`, `audience`, `tone`, `blog_kind`, `constraints`, **`tasks`** (5–9 items).  
   Forces `blog_kind = news_roundup` when `mode == open_book`.

5. **Fan-out: orchestrator → worker (parallel sends)**  
   One **Send** per `Task` in `plan.tasks`, each with task snapshot + topic + mode + evidence.

6. **worker**  
   Writes one Markdown section per task: `##` heading, bullets covered, citations/evidence rules per mode.  
   Returns `sections: [(task.id, section_md)]`.

7. **reducer** (subgraph, sequential)  
   - **merge_content** → `merged_md`  
   - **decide_images** → placeholders + `image_specs` (max 3 images)  
   - **generate_and_place_images** → writes images under `images/`, replaces placeholders, writes `.md`, sets `final`

8. **END**

The **notebook** `1_bwa_basic.ipynb` implements a **smaller** graph: orchestrator → fan-out → worker → single reducer that only concatenates sections (no router/research/images).

---

## 5. Node reference (production graph)

### 5.1 `router_node`

- **Input:** `topic`, `as_of`.  
- **Output:** `needs_research`, `mode`, `queries`, `recency_days`.  
- **Purpose:** Classify whether the topic needs live web context and which “book” style applies (evergreen vs news).

### 5.2 `research_node`

- **Input:** `queries`, `as_of`, `recency_days`, `mode`.  
- **Output:** `evidence` (may be empty if no key or no results).  
- **Purpose:** Gather and normalize web evidence for hybrid/open_book planning and writing.

### 5.3 `orchestrator_node`

- **Input:** `topic`, `mode`, `as_of`, `recency_days`, `evidence`.  
- **Output:** `plan` (`Plan`).  
- **Purpose:** Turn topic + evidence into a structured outline with **tasks**.

### 5.4 `fanout` (conditional edge function)

- **Input:** `plan`, `topic`, `mode`, `as_of`, `recency_days`, `evidence`.  
- **Output:** List of `Send("worker", payload)` — one per task.  
- **Purpose:** Parallel section generation.

### 5.5 `worker_node`

- **Input:** Per-send payload with `task`, `plan`, `topic`, `mode`, `as_of`, `recency_days`, `evidence`.  
- **Output:** `sections: [(task_id, section_md)]`.  
- **Purpose:** Single section Markdown aligned with task goals, bullets, tags, and citation requirements.

### 5.6 Reducer subgraph

| Sub-node | Purpose |
|----------|---------|
| `merge_content` | Sort sections by `task_id`, join into one `# Title` document → `merged_md`. |
| `decide_images` | LLM proposes up to 3 `ImageSpec` entries and inserts `[[IMAGE_n]]` into copy → `md_with_placeholders`, `image_specs`. |
| `generate_and_place_images` | For each spec: generate bytes (OpenAI `gpt-image-1`, fallback Gemini), save under `images/`, replace placeholder with `![alt](images/file)` + caption; on failure, insert a quoted error block. Always writes final `{slug}.md` and sets `final`. |

---

## 6. Task model (`Task` in `Plan`)

Each **task** is one section of the blog. Fields drive worker prompts and ordering.

| Field | Meaning |
|-------|---------|
| `id` | Integer order key; **merge_content** sorts sections by this. |
| `title` | Section heading theme. |
| `goal` | One-sentence reader outcome. |
| `bullets` | 3–6 outline bullets the section must cover in order. |
| `target_words` | Desired length (120–550 range in schema). |
| `tags` | Optional labels; UI may aggregate up to 5 for Dev.to publish. |
| `requires_research` | Section expects research-backed content. |
| `requires_citations` | External claims should cite evidence URLs (hybrid). |
| `requires_code` | At least one code snippet if true. |

**Plan-level fields:** `blog_title`, `audience`, `tone`, `blog_kind` (`explainer` \| `tutorial` \| `news_roundup` \| `comparison` \| `system_design`), `constraints`, `tasks`.

---

## 7. Frontend (`bwa_frontend.py`) behavior

- **Sidebar:** Topic, as-of date, **Generate Blog**; **Past blogs** loads a previous `.md` into session state (plan/evidence may be absent for old files).
- **Run:** Builds initial dict matching `State` keys, then `try_stream(app, inputs)` — prefers `stream_mode="updates"`, falls back to `"values"`, then plain `invoke`.
- **Tabs:** Plan (dataframe + JSON), Evidence, Markdown preview (local image resolution), Images (specs + files), Logs.
- **Downloads:** Raw `.md`, zip bundle (markdown + `images/`), images-only zip.
- **Publish:** If `publish` imports cleanly, shows Dev.to/Medium checkboxes, draft flag, Cloudinary upload toggle, tag extraction from tasks, validation that no local image paths remain before publish when needed.

---

## 8. Publishing and images (`publish.py`)

- **Cloudinary:** If configured, rewrites `![...](local/path)` to `https://...` for remote hosts.  
- **Dev.to:** `POST https://dev.to/api/articles` with optional `cover_image` (first `https` image in markdown). Tags normalized (lowercase alphanumeric, max 4).  
- **Medium:** `GET /v1/me` then `POST /v1/users/{id}/posts` with markdown content.  
- **Safety:** `markdown_still_has_local_image_paths` blocks publish when platforms cannot resolve paths.

---

## 9. Environment variables

| Variable | Used for |
|----------|----------|
| `OPENAI_API_KEY` | Chat (`gpt-4.1-mini`), structured outputs, OpenAI image generation. **Required** for core app. |
| `TAVILY_API_KEY` | Tavily search in `research_node`. Optional. |
| `GOOGLE_API_KEY` | Gemini image fallback when OpenAI image gen fails. Optional. |
| `DEVTO_API_KEY` | Dev.to publish. Optional. |
| `MEDIUM_INTEGRATION_TOKEN` | Medium publish. Optional. |
| `CLOUDINARY_URL` or `CLOUDINARY_*` | Upload local images before publish. Optional. |
| `CLOUDINARY_FOLDER` | Upload folder prefix (default `blog-writing-agent`). Optional. |

---

## 10. Notebooks (development trajectory)

| Notebook | Typical focus |
|----------|----------------|
| `1_bwa_basic.ipynb` | Minimal LangGraph: plan → parallel workers → concatenate → save `.md`. |
| `2_bwa_improved_prompting.ipynb` | Prompt/schema iterations. |
| `3_bwa_research.ipynb` | Research integration experiments. |
| `4_bwa_research_fine_tuned.ipynb` | Further research tuning. |
| `5_bwa_image.ipynb` | Image pipeline experiments. |
| `tavily_test.ipynb` | Tavily tooling tests. |

Production behavior is defined in **`bwa_backend.py`** + **`bwa_frontend.py`**.

---

## 11. Summary

The architecture is a **router → optional research → plan → parallel section writers → merge → optional image plan → generate/place images → file output** pipeline, with a **Streamlit** shell for interaction and **optional** web publishing. Understanding **`State`**, **`Task`/`Plan`**, and the **reducer subgraph** is enough to trace every step from topic input to final markdown and assets.
