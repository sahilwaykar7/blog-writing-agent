# Blog Writing Agent

A LangGraph-based blog writing agent with a Streamlit UI. It plans, researches (optional), writes sections, and can add AI-generated images to technical blog posts.

---

## Steps to run on your laptop

### 1. Prerequisites

- **Python 3.10+** (check with `python3 --version`)
- **OpenAI API key** (required for the agent)

### 2. Clone and enter the project (if not already)

```bash
cd /path/to/blog-writing-agent
```

### 3. Create a virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# Windows: venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Add a `.env` file with your LLM (model) API key

You **must** create a `.env` file in the project root and add your OpenAI API key (the LLM model key). Without it, the app will not run.

**Option A – copy the example and edit:**

```bash
cp .env.example .env
```

Then open `.env` and replace `sk-your-openai-api-key` with your real key.

**Option B – create `.env` manually** with at least:

```bash
# Required: LLM model key (OpenAI)
OPENAI_API_KEY=sk-your-openai-api-key
```

- **OPENAI_API_KEY** – **Required.** This is the LLM model key. Get it from [OpenAI API keys](https://platform.openai.com/api-keys).
- **TAVILY_API_KEY** – Optional. Enables web search for “research” topics. Get it from [Tavily](https://tavily.com).
- **GOOGLE_API_KEY** – Optional. Used only as a fallback if OpenAI image generation fails. Get it from [Google AI Studio](https://aistudio.google.com/apikey).

### 6. Run the app

From the project root (with `venv` activated):

```bash
streamlit run bwa_frontend.py
```

Your browser should open to **http://localhost:8501**. If it doesn’t, open that URL manually.

### 7. Use the app

1. Enter a **topic** in the sidebar (e.g. “Introduction to LangGraph”).
2. Optionally change the **As-of date**.
3. Click **Generate Blog**.
4. Wait for the run to finish, then check the **Plan**, **Evidence**, **Markdown Preview**, **Images**, and **Logs** tabs.

Generated markdown is saved as `*.md` in the project folder; if images are generated, they go into an `images/` folder.

### 8. Publish to Dev.to or Medium

After a blog is generated, open the **Markdown Preview** tab and scroll to **Publish to web**. Add API keys to `.env`:

- **Dev.to:** [Settings → Account → DEV API Keys](https://dev.to/settings/extensions) → create a key → add `DEVTO_API_KEY=...` to `.env`.
- **Medium:** [Settings → Integration tokens](https://medium.com/me/settings/security) → create a token → add `MEDIUM_INTEGRATION_TOKEN=...` to `.env`.

Then check **Publish to Dev.to** and/or **Publish to Medium**, optionally check **Publish as draft**, and click **Publish**. The post URL will appear on success.

---

## Optional: image generation fallback

By default, the app now uses your existing `OPENAI_API_KEY` for image generation too.

If OpenAI image generation fails and you want a fallback provider, add `GOOGLE_API_KEY=...` to your `.env` file. The app will then try Gemini automatically as a fallback.

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| `OPENAI_API_KEY` error | Create `.env` in the project root with `OPENAI_API_KEY=sk-...`. |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` inside your venv. |
| Port 8501 in use | Run `streamlit run bwa_frontend.py --server.port 8502` (or another free port). |
| Research returns no results | Set `TAVILY_API_KEY` in `.env` if you want web search. |
| Images not generated | OpenAI image generation is tried first. If that fails, set `GOOGLE_API_KEY` for Gemini fallback and retry. |
| Publish failed | Ensure `DEVTO_API_KEY` or `MEDIUM_INTEGRATION_TOKEN` is set in `.env` and valid. |

---

## Project layout

- **bwa_backend.py** – LangGraph pipeline (router → research → plan → workers → reducer/images).
- **bwa_frontend.py** – Streamlit UI; run with `streamlit run bwa_frontend.py`.
- **publish.py** – Publish posts to Dev.to and Medium (optional; requires `requests` and API keys in `.env`).
- **1_bwa_basic.ipynb … 5_bwa_image.ipynb** – Jupyter notebooks for development/experiments.
