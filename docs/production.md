# Production runbook

Manual deploy of AI Support Hub on the Oracle VPS. Local development still uses `docker-compose.yml` and [onboarding.md](onboarding.md).

Do not put real passwords, API keys, TLS private keys, SSH keys, or GitHub tokens in Git or the Vault. The server file `/opt/ai-support-hub/.env.production` is mode `0600` and is the only place those values live until a future CI secret store exists.

## Host layout

| Item | Value |
| --- | --- |
| Public IP | `147.15.91.116` |
| SSH user | `ubuntu` |
| Application directory | `/opt/ai-support-hub` |
| Environment file | `/opt/ai-support-hub/.env.production` (mode `0600`) |
| Backups | `/opt/ai-support-hub/backups/` |
| Nginx site | `/etc/nginx/sites-available/ai-support-hub` |
| Compose file | `compose.production.yml` |

Use `sudo docker` for every Docker command. Do not add operators to the `docker` group.

Clone a recorded revision of `main`. Do not deploy `feat/foundation`.

```bash
sudo mkdir -p /opt/ai-support-hub
sudo chown ubuntu:ubuntu /opt/ai-support-hub
cd /opt/ai-support-hub
git clone git@github.com:DavidGBbr/AI-Support-Hub.git .
git checkout <recorded-commit-sha>
```

The VPS uses a read-only GitHub deploy key at `/opt/ai-support-hub/.ssh/github_deploy`. Keep that private key on the server only.

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
| Worker dispatch | `POST http://<origin>/api/diagnostics/worker` |
| Worker status | `GET http://<origin>/api/diagnostics/worker/<task_id>` |

After TLS, use `https://<domain>` for the same paths. HTTP must redirect to HTTPS.

## Start, stop, logs

From `/opt/ai-support-hub`:

```bash
sudo docker compose --env-file .env.production -f compose.production.yml config
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

Record the current Git SHA before changing anything.

1. `cd /opt/ai-support-hub`
2. `git fetch origin`
3. `git checkout <recorded-main-commit-sha>`
4. Confirm `.env.production` is mode `0600` and does not use `.env.example` values
5. `sudo docker compose --env-file .env.production -f compose.production.yml config`
6. `sudo docker compose --env-file .env.production -f compose.production.yml up -d --build`
7. Wait until `postgres`, `redis`, `api`, and `web` are healthy: `sudo docker compose --env-file .env.production -f compose.production.yml ps`
8. `sudo docker compose --env-file .env.production -f compose.production.yml exec api alembic upgrade head`
9. HTTP checks:

   ```bash
   curl -fsS http://127.0.0.1:3000/ >/dev/null
   curl -fsS http://127.0.0.1:8000/health
   curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/
   curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health
   curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health/dependencies
   ```

10. Queue the diagnostic worker and poll until `SUCCESS`:

    ```bash
    curl -s -X POST -H 'Host: <domain-or-ip>' http://127.0.0.1/api/diagnostics/worker
    curl -s -H 'Host: <domain-or-ip>' http://127.0.0.1/api/diagnostics/worker/TASK_ID
    ```

11. Inspect logs if any check fails:

    ```bash
    sudo docker compose --env-file .env.production -f compose.production.yml logs --tail=200
    ```

12. Confirm loopback-only publish and no public Postgres/Redis:

    ```bash
    sudo ss -ltnp | grep -E ':3000|:8000|:5432|:6379'
    sudo docker compose --env-file .env.production -f compose.production.yml ps --format json
    ```

Web and API must show `127.0.0.1:3000` and `127.0.0.1:8000`. Postgres and Redis must have no host ports.

## Database backup

Retention on this host: keep dated dumps for 7 days under `/opt/ai-support-hub/backups/`. Choose off-host retention before storing customer data.

```bash
cd /opt/ai-support-hub
mkdir -p backups
chmod 700 backups
set -a
# shellcheck disable=SC1091
. ./.env.production
set +a
stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="backups/aisupporthub-${stamp}.sql"
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$dump"
chmod 600 "$dump"
find backups -type f -name 'aisupporthub-*.sql' -mtime +7 -delete
```

### One-time restore drill

Run this before live customer data exists. It replaces the current database.

```bash
cd /opt/ai-support-hub
set -a
. ./.env.production
set +a
dump=<path-to-dump.sql>
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();"
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"
sudo docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$dump"
curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health/dependencies
```

## Rollback

Schema migrations must be backward compatible before a release can be rolled back safely. Record the previous SHA at deploy time.

1. `cd /opt/ai-support-hub`
2. `git fetch origin`
3. `git checkout <previous-recorded-commit-sha>`
4. `sudo docker compose --env-file .env.production -f compose.production.yml up -d --build`
5. Wait for health checks in `docker compose ps`
6. `curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health`
7. `curl -fsS -H 'Host: <domain-or-ip>' http://127.0.0.1/api/health/dependencies`

If the failed release already applied a forward-only migration, restore the matching database dump first, then check out the previous SHA.

## Operator checks

- Certificate renewal (after TLS exists): `sudo certbot renew --dry-run` and `systemctl list-timers | grep certbot`
- Disk: `df -h /` and `sudo du -sh /var/lib/docker /opt/ai-support-hub/backups`
- Docker logs: bounded by `/etc/docker/daemon.json` (`local` driver, `10m` x `3` files)
- Docker status: `sudo systemctl is-enabled docker containerd nginx` and `sudo systemctl is-active docker containerd nginx`
- Published ports: `sudo ss -ltnp` — expect `22`, `80`, `443` (after TLS), plus loopback `3000`/`8000`
- Secrets: add values only to `/opt/ai-support-hub/.env.production` or the future CI secret store. Never commit them.

Reboot only in a maintenance window. After reboot, repeat the HTTP health checks.

## Firewall

Keep the existing UFW set. Do not delete iptables rules by position (for example `iptables -D INPUT 5`); UFW owns those chains. After Docker is installed, confirm web/API are loopback-only. Docker-published ports can bypass ordinary UFW filtering.
