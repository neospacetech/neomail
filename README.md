# NeoMail

Self-hosted mail for NeoSuite: a mail server and a multi-account client, aware of your calendar, tasks and contacts.

## Domain

- **Mailboxes** (`neomail.Mailbox`): folders per owner with JMAP / RFC 6154 roles (inbox, drafts,
  sent, archive, junk, trash, custom). Names are hierarchical (`Projects/Acme`) and unique per
  owner ignoring case; every role except custom is unique too.
- **Messages** (`neomail.Message`): addresses are parsed per RFC 5322 (quoted display names,
  plus tags, internationalised addresses), recipients are deduplicated across To, Cc and Bcc,
  and subjects are whitespace-normalised.
- **Threads** (`neomail.Thread`): messages group by `References` and `In-Reply-To` (including
  replies to a message that never arrived), and reference-less replies join by base subject
  (`Re:`, `Fwd:`, `AW:`, `[list]` tags and the like stripped). Grouping is independent of
  arrival order.
- **Smart Send**: before a message leaves, `POST /api/v1/smart-send/check` checks the draft's
  claims (meeting times, stated availability, presence) against the sender's calendar, and its
  mentions of attachments and people against what the draft contains. Findings carry a
  severity, a one-sentence reason and the calendar objects behind them; a conflict stops
  `POST /api/v1/messages/send` unless the sender confirms.

Outgoing mail is submitted over JMAP to Stalwart (`deploy/compose.yaml`); without a configured
server the backend keeps submissions in memory. Changes are emitted as CloudEvents
(`neomail.message.received`, `…sent`, `…moved`, `…marked`, `neomail.mailbox.*`) and streamed at
`GET /api/v1/changes`. NeoFlow can invoke `neomail.message.send|move|mark` and
`neomail.smartsend.check`.

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
