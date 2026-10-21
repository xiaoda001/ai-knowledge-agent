# Development conventions

## Frontend (`apps/web/src`)

- Keep React pages, reusable components, API access, and pure utilities in separate areas:
  - `pages/`: page-level composition and page state.
  - `components/`: focused UI components with explicit props.
  - `server/`: all backend calls; centralize `fetch`, auth headers, JSON/error handling, and endpoint functions here.
  - `utils/`: reusable pure helpers that do not render UI or perform network requests.
- Components must not call `fetch` directly. Components call named functions from `server/`.
- Prefer small named ES module exports and import only what a module uses. Avoid side-effect imports except styles and required initialization so Vite can tree-shake unused code. Keep CSS listed as the package's explicit side effect.
- Keep files focused. Aim for roughly 200 lines or fewer; when a file grows beyond that, split it by responsibility if that makes the code easier to review. Avoid splitting tiny, tightly coupled helpers just to meet a line count. Do not accumulate page, API, parsing, and formatting logic in one file.
- Keep authorization decisions on the server. Frontend visibility is a usability aid only.

## Backend (`apps/server`)

- `app/main.py` only configures FastAPI, middleware, startup hooks, and router registration.
- `app/api/routes/` groups HTTP endpoints by resource. Routes validate transport input and delegate nontrivial or reusable business logic to services or agents; keep small resource queries local to their route module.
- `app/api/schemas.py` contains request/response schemas; `app/api/dependencies.py` contains request-scoped dependencies and identity resolution.
- `app/services/` contains application business services that do not belong to HTTP transport.
- Keep API and agent code in separate packages. API modules own HTTP behavior; `app/agents/` owns retrieval graphs, agent orchestration, and model-provider boundaries.
- Put shared database models, settings, ACL checks, and embedding configuration in `packages/server-core/`; keep Celery task orchestration in `apps/worker/worker_app/`.
- Split modules by responsibility rather than growing large route or task files. Keep errors safe for clients and never log credentials, raw prompts, or unredacted enterprise content.

## Agent modules

- Put graph orchestration and retrieval strategies under `apps/server/app/agents/knowledge_qa/`.
- Put provider selection and outbound redaction under `apps/server/app/agents/providers/`.
- Apply authorization before candidate retrieval and keep LLM egress policy at the provider boundary.
- Do not let an agent choose or widen its own ACL scope; pass server-computed authorized context into the graph.
- Chat intent routing may select only fixed application branches; system-count operations must derive user scope from the authenticated server identity and reuse ACL helpers.
- Do not expose generic SQL/database tools, open-ended ReAct loops, or model-supplied user/role identifiers to chat orchestration.
