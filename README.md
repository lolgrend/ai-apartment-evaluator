# AI Apartment Evaluator

A practical FastAPI application for evaluating apartment listings with LLMs.

This project is not a toy chat wrapper. It is a small, deployable AI application
that shows how I approach LLM features as software engineering work: model
routing, structured outputs, vision input, tool use, observability, guardrails,
tests, and deployment concerns.

## What It Does

- Scrapes or accepts pasted apartment listings.
- Sends listing text and selected images to an LLM through LiteLLM.
- Produces a structured evaluation with score, recommendation, extracted facts,
  pros, cons, and reasoning.
- Detects floor-plan images with a combination of scraper metadata and model
  vision.
- Provides a listing-specific chat interface.
- Lets the chat use a read-only tool to compare the current listing with saved
  listings.
- Traces LLM calls and application-level workflows with Langfuse.
- Applies simple runtime guardrails for obvious prompt-injection attempts before
  calling the model.

## Why This Project Exists

The goal is to demonstrate practical AI application engineering:

- building around a real workflow instead of a generic demo,
- routing model calls through a configurable gateway,
- measuring LLM behavior with traces, sessions, metadata, token usage, and
  guardrail observations,
- using structured output where correctness matters,
- keeping tool access read-only and scoped,
- testing the integration paths that tend to break.

## Stack

- Python, FastAPI, Jinja2
- SQLite, SQLAlchemy
- LiteLLM-compatible Chat Completions API
- Langfuse Python SDK
- httpx, BeautifulSoup, Playwright
- Docker Compose
- unittest and GitHub Actions

## AI Features

### Structured Evaluation

The evaluator asks the model for a strict JSON schema and validates the result
with Pydantic. This keeps the UI and persistence layer independent from
free-form model text.

### Vision

Listing images are fetched, size-limited, encoded, and sent as image inputs.
The model identifies which images are floor plans and returns their gallery
positions.

### Tool Use

The chat can call a read-only `get_listing_details` tool when the user asks to
compare listings. The tool exposes only application data needed for comparison
and cannot mutate state.

### Observability

Langfuse tracing captures:

- `listing-evaluation` root spans,
- `listing-chat-response` root spans,
- `litellm-chat-completion` generation observations,
- `prompt-injection-input-check` guardrail observations,
- user/session/listing metadata,
- model names, token usage when returned by the gateway, and sanitized
  inputs/outputs.

The tracing code deliberately avoids storing full image payloads and redacts
basic email/phone patterns from captured text.

### Guardrails

The chat path includes a simple input guardrail that blocks low-effort prompt
injection attempts such as requests to ignore previous instructions, reveal the
system prompt, or misuse the listing-details tool. This is not a complete LLM
security solution; it is a baseline runtime check plus Langfuse visibility that
can be replaced or extended with a dedicated guardrail service.

## Running Locally

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

Required `.env` values:

| Variable | Purpose |
| --- | --- |
| `LITE_LLM_KEY` | API key for the LiteLLM-compatible gateway. |
| `LITE_LLM_BASE_URL` | Gateway base URL, for example `http://localhost:4000`. |
| `SECRET_KEY` | Session-cookie signing secret. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Initial admin account. |
| `MODEL` | Default model alias. |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` | Optional Langfuse tracing configuration. |

If Langfuse variables are missing, tracing becomes a no-op and the application
continues to run.

## Tests

```bash
python -m unittest discover -s tests -v
```

The test suite covers:

- LiteLLM request construction,
- model selection and unsupported parameter avoidance,
- structured-output payloads,
- read-only listing tool behavior,
- prompt-injection guardrail behavior,
- Langfuse payload sanitization,
- Markdown sanitization for chat responses,
- floor-plan detection merging.

## Deployment

The repository includes a Dockerfile and Docker Compose setup. The app stores
SQLite data in a mounted `data/` directory, which is intentionally ignored by
Git.

```bash
docker compose up -d --build
```

Deployment scripts are included as examples for immutable image tags and simple
rollback. They expect a local `.env` file and a persistent `data/` volume.

## Public Repository Notes

This public version intentionally does not include real listing data, API keys,
database files, trace exports, or deployment-specific hostnames. Runtime state
lives outside Git in `.env` and `data/`.
