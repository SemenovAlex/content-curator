# VPS deployment and OpenClaw setup

Target paths:

- repo: `/opt/content-curator`
- agent: `curator`
- workspace: `/home/dtadmin/.openclaw/workspace-curator`
- timezone: `Europe/Moscow`
- Obsidian digest dir: `/home/dtadmin/obsidian-vault/Digital Twin/90 Agent/Content Curator/Digests`

## 1. Clone and install

```bash
cd /opt
git clone git@github.com:SemenovAlex/content-curator.git
sudo chown -R dtadmin:dtadmin /opt/content-curator
sudo -iu dtadmin
cd /opt/content-curator

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[browser,dev]'
.venv/bin/playwright install chromium
```

If Chromium reports missing shared libraries:

```bash
sudo /opt/content-curator/.venv/bin/playwright install-deps chromium
```

## 2. Runtime environment

Expose these variables to the OpenClaw Gateway process:

```dotenv
CURATOR_DATA_DIR=/opt/content-curator/data
OBSIDIAN_VAULT_PATH=/home/dtadmin/obsidian-vault
OBSIDIAN_DIGEST_DIR=Digital Twin/90 Agent/Content Curator/Digests
```

Then:

```bash
mkdir -p '/home/dtadmin/obsidian-vault/Digital Twin/90 Agent/Content Curator/Digests'
```

## 3. Deterministic checks

```bash
cd /opt/content-curator
.venv/bin/pytest -q
.venv/bin/ruff check curator tests
git diff --check
.venv/bin/curator article-sources --config /opt/content-curator/sources.yaml
```

Then run live historical checks:

```bash
.venv/bin/python scripts/check_acceptance.py \
  --cli /opt/content-curator/.venv/bin/curator \
  --config /opt/content-curator/sources.yaml
```

## 4. Dedicated agent

```bash
openclaw agents list --json
```

If `curator` does not exist:

```bash
openclaw agents add curator \
  --workspace /home/dtadmin/.openclaw/workspace-curator \
  --non-interactive \
  --json
```

If it exists but uses another workspace:

```bash
openclaw config set agents.entries.curator.workspace /home/dtadmin/.openclaw/workspace-curator
```

## 5. Install the skill

```bash
openclaw skills install /opt/content-curator/skill \
  --as content-curator \
  --agent curator \
  --force

openclaw skills info content-curator --agent curator --json
openclaw skills check --agent curator
```

Optional: restrict the agent's skill allowlist:

```bash
openclaw config set agents.entries.curator.skills '["content-curator"]'
```

## 6. Sandbox and exec policy

```bash
openclaw config set agents.entries.curator.sandbox.mode all
openclaw config set agents.entries.curator.sandbox.scope agent
openclaw config set agents.entries.curator.sandbox.workspaceAccess rw
openclaw config set agents.entries.curator.tools.exec.host gateway
openclaw config set agents.entries.curator.tools.exec.mode allowlist
```

Allowlist only the deterministic CLI:

```bash
openclaw approvals allowlist add \
  --gateway \
  --agent curator \
  '/opt/content-curator/.venv/bin/curator'
```

Do not enable global `yolo`/`full` and do not grant this host permission to `main`.

Recreate/inspect the sandbox and approvals:

```bash
openclaw sandbox recreate --agent curator --force
openclaw sandbox explain --agent curator
openclaw approvals get --gateway
```

Expected posture: sandbox=`all`, scope=`agent`, workspace=`rw`, exec host=`gateway`, mode=`auto`, exact curator binary allowlisted.

## 7. Full manual run

```bash
openclaw agent \
  --agent curator \
  --message '$content-curator Prepare and publish the complete article digest for 2026-09-18 using the Europe/Moscow date.'
```

Verify:

```bash
ls -l '/home/dtadmin/obsidian-vault/Digital Twin/90 Agent/Content Curator/Digests/2026-09-18.md'

/opt/content-curator/.venv/bin/curator list-ingest \
  --date 2026-09-18 \
  --config /opt/content-curator/sources.yaml

/opt/content-curator/.venv/bin/curator list-analysis \
  --date 2026-09-18 \
  --config /opt/content-curator/sources.yaml

test ! -e /opt/content-curator/data/runs/2026-09-18/digest.md
```

## 8. Keep Gateway/scheduler alive after logout

```bash
sudo loginctl enable-linger dtadmin
```

## 9. Daily automation

```bash
openclaw automations create '0 6 * * *' \
  '$content-curator Prepare and publish the complete article digest for yesterday using the Europe/Moscow date. Do not send the digest to chat.' \
  --name 'Daily content curator' \
  --agent curator \
  --session isolated \
  --tz Europe/Moscow \
  --exact \
  --timeout-seconds 3600 \
  --no-deliver
```

Verify and force a test run:

```bash
openclaw automations list --agent curator --json
openclaw automations run '<JOB_ID>' --wait --wait-timeout 60m --poll-interval 5s
openclaw automations runs '<JOB_ID>' --limit 10 --json
```

Do not create a parallel systemd ingest timer. A separate timer is acceptable only for deterministic cleanup:

```bash
/opt/content-curator/.venv/bin/curator cleanup --config /opt/content-curator/sources.yaml
```

## Troubleshooting

If a source fails, run only that source with `discover-articles`, then a stateless ingest. If publication refuses, run `list-ingest`, `list-analysis`, then `finalize-day`; the latter names missing IDs. Never bypass completeness validation.
