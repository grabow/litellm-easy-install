# LiteLLM Local Setup Guide

This repository starts a local LiteLLM proxy with PostgreSQL by using Docker Compose.

The guide below is written for students and admins who want a simple local setup without installing LiteLLM manually on the host system.

## What this project does

When you start this repository, Docker launches:

- a PostgreSQL database
- a LiteLLM proxy on port `4000`

The LiteLLM proxy reads its model and database configuration from:

- `.env`
- `config.yaml`

## Requirements

Before you start, make sure the following tools are installed:

- Docker
- Docker Compose

You can verify this with:

```bash
docker --version
docker compose version
```

## Step 1: Open the project folder

Open a terminal in this repository.

Example:

```bash
cd hsog-litellm-easy
```

## Step 2: Create your environment file

Copy the example environment file:

```bash
cp .env.example .env
```

This creates a local `.env` file that Docker Compose will use when starting the containers.

## Step 3: Edit `.env`

Open `.env` and set the required values.

Important variables:

- `POSTGRES_USER`: database user name
- `POSTGRES_PASSWORD`: database password
- `POSTGRES_DB`: database name
- `DATABASE_URL`: connection string used by LiteLLM
- `LITELLM_MASTER_KEY`: master key for accessing LiteLLM
- `CAMPUS_GPT_API_BASE`: base URL of the upstream Campus GPT API
- `CAMPUS_GPT_API_KEY`: API key for the upstream Campus GPT endpoint

Example:

```env
POSTGRES_USER=litellm
POSTGRES_PASSWORD=change-me
POSTGRES_DB=litellm
DATABASE_URL=postgresql://litellm:change-me@db:5432/litellm
LITELLM_MASTER_KEY=change-me
CAMPUS_GPT_API_BASE=dummy-url
CAMPUS_GPT_API_KEY=change-me
```

Notes:

- If you change `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB`, you must also update `DATABASE_URL`.
- `CAMPUS_GPT_API_BASE` should include the full LiteLLM-compatible API base, for example `https://example.org/v1`.
- Choose strong values for `POSTGRES_PASSWORD` and `LITELLM_MASTER_KEY`.

## Step 4: Start LiteLLM

Run:

```bash
docker compose up -d
```

What this does:

- creates the Docker network
- starts PostgreSQL
- waits until PostgreSQL is healthy
- starts LiteLLM

The first startup can take a little longer because Docker may need to download the images.

## Step 5: Check if everything is running

Check the container status:

```bash
docker compose ps
```

You should see:

- the `db` service as `healthy`
- the `litellm` service as `up`

Docker Compose creates container names automatically. Typical names look like:

- `hsog-litellm-easy-db-1`
- `hsog-litellm-easy-litellm-1`

You can also test the LiteLLM health endpoint:

```bash
curl http://localhost:4000/health/liveliness
```

Expected response:

```text
"I'm alive!"
```

## Step 6: Access LiteLLM

After startup, LiteLLM is available at:

```text
http://localhost:4000
```

## Useful commands

Show running containers:

```bash
docker compose ps
```

Show logs:

```bash
docker compose logs -f
```

Show only LiteLLM logs:

```bash
docker compose logs -f litellm
```

Show only PostgreSQL logs:

```bash
docker compose logs -f db
```

## Stop the setup

To stop the containers:

```bash
docker compose down
```

This stops and removes the containers, but keeps the PostgreSQL data volume.

## Reset everything

If you want to remove all local PostgreSQL data and start from scratch:

```bash
docker compose down -v
```

Use this if:

- you want a clean reinstall
- you changed database settings and want a fresh start
- you are only testing locally and do not need existing data

## Troubleshooting

If `docker compose up -d` fails:

1. Check whether Docker is running.
2. Run `docker compose ps` to inspect service state.
3. Run `docker compose logs -f` to inspect errors.
4. If needed, reset the setup with `docker compose down -v` and start again.

If Docker reports a container name conflict such as `litellm-db is already in use`, remove the old manually created containers once:

```bash
docker rm -f litellm-db litellm
```

Then start the stack again:

```bash
docker compose up -d
```

If LiteLLM does not respond on port `4000`:

1. Check `docker compose ps`.
2. Check `docker compose logs -f litellm`.
3. Confirm that `.env` contains valid values for `CAMPUS_GPT_API_BASE` and `CAMPUS_GPT_API_KEY`.
