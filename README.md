# NeoMail

Self-hosted mail for NeoSuite: a mail server and a multi-account client, aware of your calendar, tasks and contacts.

Status: scaffold. The `Item` model is a placeholder domain to replace.

## Layout

```text
├── engine/        Rust workspace: neomail-core (logic) and neomail-py (PyO3 bindings, wheel `neomail_core`)
├── backend/       FastAPI service, package `neomail`
├── frontend/      @neospacetech/neomail-ui: screens, widgets and NeoMind context
├── contracts/     types, events, actions and the OpenAPI document
├── deploy/        Dockerfile.backend and the Compose fragment
└── neosuite.toml  component descriptor
```

## Develop

Requirements: Rust (stable), Python 3.12+, Node 22.

```sh
python -m venv .venv && . .venv/bin/activate
pip install "maturin>=1.9,<2"
(cd engine && cargo test --workspace)
maturin develop -m engine/py/Cargo.toml
pip install -e "backend[dev]"
cd backend && pytest && ruff check . && mypy
uvicorn neomail.app:app --reload
```

Settings are read from `NEOMAIL_*` environment variables.

### Frontend

`frontend/` is a source-only package consumed by the neosuite-app shell. It expects
`neosuite-commons` checked out next to this repository.

```sh
cd frontend
npm ci
npm run typecheck
```

## Container

```sh
docker build -f deploy/Dockerfile.backend -t neomail-backend .
docker run --rm -p 8000:8000 neomail-backend
```
