# Talon / NanoClaw Deployment Plan

## Prerequisites

- [ ] Anthropic API key (Claude) — Talon is designed for Claude, not OpenAI-compatible APIs
  - Get this from your mentor
- [ ] Node.js 18+ (Talon is a Node.js project: `github.com/taylorwalton/talon`)
- [ ] Valid Groq key already set in `.env` — used by `copilot-mcp` for other features

---

## Fixes Applied (May 25 Session)

### Graylog pipeline 500 crash
**Files:** `backend/app/connectors/graylog/utils/universal.py`, `backend/app/connectors/graylog/services/pipelines.py`

Graylog isn't deployed, but the frontend calls `/api/graylog/pipeline/full` which
raised `HTTPException(500)` when it couldn't reach `127.1.1.1`. Fixed to return
`{success: False}` with empty data instead of crashing.

### Agents sync 500 crash (Velociraptor)
**File:** `backend/app/agents/routes/agents.py`

`sync_agents_velociraptor()` was crashing the entire agents sync endpoint
because it tries to read `/app/velociraptor-config.yaml` which doesn't exist
in the backend container. Fixed by wrapping it in try/except — Wazuh agents
sync succeeds, Velociraptor fails gracefully with a log.

### Wazuh Indexer not reachable (ClusterIP)
**File:** `manifests/wazuh-indexer-lb.yaml`

The Helm chart deploys the indexer API as `ClusterIP` (internal to Kubernetes
only). CoPilot's Docker containers couldn't reach `10.244.222.140:9200`.
Created a standalone LoadBalancer service manifest:

```bash
kubectl apply -f manifests/wazuh-indexer-lb.yaml
```

Also need to verify the connectors in CoPilot after applying:

```bash
cd /home/ubuntu/ju-nine/projects/wazuh/copilot/CoPilot
docker compose exec copilot-backend python3 -c "
import asyncio
from app.db.db_session import get_db_session
from app.connectors.models import Connectors
from app.connectors.services import ConnectorServices
from sqlalchemy.future import select

async def main():
    async with get_db_session() as session:
        for cid in [1, 2]:
            response = await ConnectorServices.verify_connector_by_id(cid, session)
            print(f'ID={cid}: {response}')
asyncio.run(main())
"

## Deployment Steps

### 1. Clone & Build Talon inside the VM

```bash
cd /home/ubuntu
git clone https://github.com/taylorwalton/talon.git
cd talon
# Build the TypeScript project
npm install
npm run build   # compiles to dist/index.js
```

### 2. Create `.env` for Talon

Copy `.env.example` to `.env` and set:

```env
# Talon needs read-only MySQL access (same creds as CoPilot)
MYSQL_HOST=copilot-mysql
MYSQL_PORT=3306
MYSQL_USER=copilot
MYSQL_PASSWORD=<from .env>
MYSQL_DATABASE=copilot

# CoPilot REST API for write-back
COPILOT_URL=http://copilot-backend:5000
COPILOT_USERNAME=<admin username>
COPILOT_PASSWORD=<admin password>
COPILOT_SSL_VERIFY=false

# Claude API key (Anthropic)
# Not OpenAI/Groq — Talon uses `claude`/Anthropic SDK
CLAUDE_CODE_OAUTH_TOKEN=<anthropic-key>

# OpenSearch/Wazuh indexer for SIEM queries
OPENSEARCH_HOSTS=https://10.244.222.140:9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=<wazuh-indexer-password>
VERIFY_CERTS=false
```

### 3. Run Talon

**Option A — Docker container** (add to `docker-compose.yml`):

```yaml
talon:
    image: node:18
    working_dir: /app
    command: node dist/index.js
    volumes:
        - /home/ubuntu/talon:/app
        - /home/ubuntu/talon/.env:/app/.env
    ports:
        - "3100:3100"
    depends_on:
        - copilot-mysql
        - copilot-backend
    restart: always
```

Then update `.env`:
```
TALON_URL=http://talon:3100
TALON_API_KEY=<set-a-key>
```

**Option B — Run directly on VM** (simpler for testing):

```bash
cd /home/ubuntu/talon
node dist/index.js &
```

### 4. Update CoPilot `.env`

Once Talon is running:
```
TALON_URL=http://talon:3100    # or http://127.1.1.1:3100 for direct
TALON_API_KEY=<same-key-as-above>
```

Then restart the backend:
```bash
cd /home/ubuntu/ju-nine/projects/wazuh/copilot/CoPilot
docker compose up -d --force-recreate copilot-backend
```

### 5. Enable per-customer AI trigger

In the CoPilot UI, navigate to the customer settings and enable
**"AI Analyst auto-trigger"** — this sets
`incident_management_ai_analyst_trigger_enabled` for that customer.

## Why not Groq?

Talon uses the Anthropic Claude SDK and `claude` CLI under the hood. The
LLM calls go through OneCLI (Anthropic gateway) or direct Claude auth.
Groq is OpenAI-compatible, which Talon doesn't natively support.

The `copilot-mcp` container in the current stack *does* use Groq via
`OPENAI_BASE_URL`, but that's for a different purpose (MCP tool
routing), not the AI Analyst investigation pipeline.
