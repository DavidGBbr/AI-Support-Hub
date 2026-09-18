# Production runbook

Manual deploy of AI Support Hub on the Oracle VPS. Local development still uses `docker-compose.yml` and [onboarding.md](onboarding.md).

Do not put real passwords, API keys, TLS private keys, SSH keys, or GitHub tokens in Git. The server file `/opt/ai-support-hub/.env.production` is mode `0600` and is the only place those values live until a future CI secret store exists.

## Host layout

| Item | Value |
| --- | --- |
| Public IP | `147.15.91.116` |
| SSH user | `ubuntu` |
| Application directory | `/opt/ai-support-hub` |
| Environment file | `/opt/ai-support-hub/.env.production` (mode `0600`) |
| Backups | `/opt/ai-support-hub/backups/` |
| Nginx site | `/etc/nginx/sites-available/ai-support-hub` |
| Compose file | `compose.production.yml` (project `aisupport-prod`) |

Use `sudo docker` for every Docker command. Do not add operators to the `docker` group.

Clone a recorded revision of `main`. Do not deploy `feat/foundation`.

```bash
sudo mkdir -p /opt/ai-support-hub
sudo chown ubuntu:ubuntu /opt/ai-support-hub
cd /opt/ai-support-hub
git clone git@github.com:DavidGBbr/AI-Support-Hub.git .
git checkout <recorded-commit-sha>
```

If the host does not yet have a read-only GitHub deploy key, copy that recorded revision over SSH instead of storing a GitHub token in `.env.production`. Keep any deploy private key on the server only.

## Environment file

```bash
cd /opt/ai-support-hub
umask 077
cp .env.production.example .env.production
chmod 600 .env.production
```

Replace every `REPLACE_WITH_*` and `<domain>` value. Postgres user and password must be unique and must not match `.env.example`.

`NEXT_PUBLIC_API_BASE_URL` is a Next.js build argument. Changing it requires rebuilding the `web` image.

Until a production domain exists, TLS must not be requested. HTTP bootstrap may use the public IP:

```bash
APP_DOMAIN=147.15.91.116
NEXT_PUBLIC_API_BASE_URL=http://147.15.91.116/api
CORS_ORIGINS=http://147.15.91.116
```

After DNS exists, set `https://<domain>` values, rebuild, then issue the certificate.

## Public routes

Nginx is the only internet-facing process. `/api/` is stripped before FastAPI.

| What | Public URL |
| --- | --- |
| Web diagnostics | `http://<origin>/` |
| API liveness | `http://<origin>/api/health` |
| PostgreSQL + Redis | `http://<origin>/api/health/dependencies` |
| Swagger | `http://<origin>/api/docs` |

Worker dispatch has no authentication. Nginx must reject it from the public internet (`allow 127.0.0.1; allow ::1; deny all;`). Run these only on the VPS:

| What | Operator URL |
| --- | --- |
| Worker dispatch | `POST http://127.0.0.1/api/diagnostics/worker` |
| Worker status | `GET http://127.0.0.1/api/diagnostics/worker/<task_id>` |

After TLS, use `https://<domain>` for the public paths. HTTP must redirect to HTTPS.

## Start, stop, logs

From `/opt/ai-support-hub`:

```bash
sudo docker compose --env-file .env.production -f compose.production.yml config --quiet
sudo docker compose --env-file .env.production -f compose.production.yml up -d --build
sudo docker compose --env-file .env.production -f compose.production.yml ps
sudo docker compose --env-file .env.production -f compose.production.yml logs -f
sudo docker compose --env-file .env.production -f compose.production.yml stop
```

Apply migrations after the API is healthy:

```bash
sudo docker compose --env-file .env.production -f compose.production.yml exec api alembic upgrade head
```

## Nginx HTTP server block

File: `/etc/nginx/sites-available/ai-support-hub`, enabled with a symlink in `sites-enabled`. Disable `/etc/nginx/sites-enabled/default` after this block works.

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 20m;

    location = /api {
        return 301 /api/;
    }

    location /api/diagnostics/ {
        allow 127.0.0.1;
        allow ::1;
        deny all;
        proxy_pass http://127.0.0.1:8000/diagnostics/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Replace `server_name _;` with the production hostname once DNS exists.

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -fsSI -H 'Host: <domain-or-ip>' http://127.0.0.1/
curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health
# From a machine that is not the VPS, this must return 403:
# curl -s -o /dev/null -w '%{http_code}' -X POST http://<origin>/api/diagnostics/worker
```

Do not add Oracle or UFW rules for ports `3000`, `5432`, `6379`, or `8000`. Keep SSH (`22/tcp`) and Nginx (`80,443/tcp`) as the only intended public inbound ports.

## TLS

Do not install Certbot or request a certificate until:

1. The production domain is chosen.
2. Its A record points to `147.15.91.116`.
3. `curl` with `Host: <domain>` succeeds on port 80 from the public internet.
4. The Let's Encrypt notice email is known.

Then:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <domain> --agree-tos -m <email> --redirect
sudo certbot renew --dry-run
```

An IP address is not an acceptable production HTTPS endpoint.

## Release procedure

Record the current Git SHA and take a verified database dump before changing code or applying migrations. Rollback of a forward-only migration depends on that dump.

1. `cd /opt/ai-support-hub`
2. Record SHA: `git rev-parse HEAD`
3. Run the Database backup steps below. Confirm the dump is non-empty (`test -s backups/aisupporthub-<stamp>.sql`) and record that path. Do not continue if this step fails.
4. `git fetch origin`
5. `git checkout <recorded-main-commit-sha>`
6. Confirm `.env.production` is mode `0600` and does not use `.env.example` values
7. `sudo docker compose --env-file .env.production -f compose.production.yml config --quiet`
8. `sudo docker compose --env-file .env.production -f compose.production.yml up -d --build`
9. Wait until `postgres`, `redis`, `api`, and `web` are healthy: `sudo docker compose --env-file .env.production -f compose.production.yml ps`
10. `sudo docker compose --env-file .env.production -f compose.production.yml exec api alembic upgrade head`
11. HTTP checks:

   ```bash
   curl -fsS http://127.0.0.1:3000/ >/dev/null
   curl -fsS http://127.0.0.1:8000/health
   curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/
   curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health
   curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health/dependencies
   ```

12. Queue the diagnostic worker from loopback and poll until `SUCCESS`:

    ```bash
    curl -s -X POST http://127.0.0.1/api/diagnostics/worker
    curl -s http://127.0.0.1/api/diagnostics/worker/TASK_ID
    ```

13. Inspect logs if any check fails:

    ```bash
    sudo docker compose --env-file .env.production -f compose.production.yml logs --tail=200
    ```

14. Confirm loopback-only publish and no public Postgres/Redis:

    ```bash
    sudo ss -ltnp | grep -E ':3000|:8000|:5432|:6379'
    sudo docker compose --env-file .env.production -f compose.production.yml ps --format json
    ```

Web and API must show `127.0.0.1:3000` and `127.0.0.1:8000`. Postgres and Redis must have no host ports.

## Database backup

Retention on this host: keep dated dumps for 7 days under `/opt/ai-support-hub/backups/`. Choose off-host retention before storing customer data.

Read `POSTGRES_USER` and `POSTGRES_DB` from the running container. Do not `source` `.env.production` in the shell; a password with metacharacters can abort or execute the backup.

```bash
set -euo pipefail
cd /opt/ai-support-hub
mkdir -p backups
chmod 700 backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="backups/aisupporthub-${stamp}.sql"
tmp="$(mktemp backups/aisupporthub.XXXXXX)"
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$tmp"
test -s "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$dump"
find backups -type f -name 'aisupporthub-*.sql' -mtime +7 -delete
echo "Backup written to $dump"
```

If `pg_dump` fails, stop. Do not `chmod`, rename, or delete older dumps after a failed dump.

### One-time restore drill

Run this before live customer data exists. It replaces the current database.

```bash
set -euo pipefail
cd /opt/ai-support-hub
dump=<path-to-dump.sql>
test -s "$dump"
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$POSTGRES_DB'\'' AND pid <> pg_backend_pid();"'
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"'
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"'
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < "$dump"
curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health/dependencies
```

## Rollback

Schema migrations must be backward compatible before a release can be rolled back safely. Record the previous SHA and the pre-deploy dump path at deploy time.

1. `cd /opt/ai-support-hub`
2. If the failed release already applied a forward-only migration, run the restore drill against the recorded dump first
3. `git fetch origin`
4. `git checkout <previous-recorded-commit-sha>`
5. `sudo docker compose --env-file .env.production -f compose.production.yml up -d --build`
6. Wait for health checks: `sudo docker compose --env-file .env.production -f compose.production.yml ps`
7. `curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health`
8. `curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health/dependencies`

## Operator checks

- Certificate renewal (after TLS exists): `sudo certbot renew --dry-run` and `systemctl list-timers | grep certbot`
- Disk: `df -h /` and `sudo du -sh /var/lib/docker /opt/ai-support-hub/backups`
- Docker logs: bounded per production service in `compose.production.yml` (`local` driver, `10m` x `3` files). Confirm with `sudo docker inspect --format '{{.HostConfig.LogConfig.Type}} {{.HostConfig.LogConfig.Config}}' <container>`
- Redis: ephemeral. Recreating the Redis container discards queued diagnostic jobs and task results. Re-run the loopback worker dispatch after an upgrade if you need a fresh result.
- Docker status: `sudo systemctl is-enabled docker containerd nginx` and `sudo systemctl is-active docker containerd nginx`
- Published ports: `sudo ss -ltnp` — expect `22`, `80`, `443` (after TLS), plus loopback `3000`/`8000`
- Secrets: add values only to `/opt/ai-support-hub/.env.production` or the future CI secret store. Never commit them.

Reboot only in a maintenance window. After reboot, repeat the HTTP health checks.

## Firewall

Keep the existing UFW set. Do not delete iptables rules by position (for example `iptables -D INPUT 5`); UFW owns those chains. After Docker is installed, confirm web/API are loopback-only. Docker-published ports can bypass ordinary UFW filtering.
