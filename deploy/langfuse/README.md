# Local Langfuse on 1Panel

This is a standalone local Langfuse stack based on Langfuse's official self-hosted Compose deployment. It includes the Langfuse web and worker services plus PostgreSQL, ClickHouse, Redis, and MinIO. Langfuse telemetry is disabled by default. No Langfuse Cloud account is used.

## Deploy in 1Panel

1. Copy `.env.example` to `.env` in this directory.
2. Replace `SERVER_LAN_IP` with the server's LAN address (or use the exact HTTPS URL configured in 1Panel). Set each password/key to a unique random value. `ENCRYPTION_KEY` must be exactly 64 hexadecimal characters. For example, on the Linux server run `openssl rand -hex 32` to generate a suitable value; use separate generated values for each field.
3. In 1Panel, open **Containers → Compose → Create**, point it to this directory's `compose.yaml`, and start the stack.
4. Open the URL in `NEXTAUTH_URL`, sign up, create an organization and project, then copy that project's public and secret API keys.
5. In the main project's `.env`, enable the integration and point it to the local Langfuse address reachable from the API container:

   ```dotenv
   OTEL_ENABLED=true
   LANGFUSE_ENABLED=true
   LANGFUSE_HOST=http://SERVER_LAN_IP:3001
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_CAPTURE_CONTENT=false
   ```

   Replace `SERVER_LAN_IP` with the same LAN IP used above. Recreate the main project's API and Worker containers after changing `.env`.

The main project can use separate Langfuse projects by assigning a different project key pair to each deployment while keeping the same `LANGFUSE_HOST`.

## Data and network

All Langfuse database, queue, ClickHouse, and object storage data is held in named Docker volumes. Keep these volumes when updating or removing the stack. The UI uses host port `3001`; MinIO media uploads use host port `9092`. These defaults avoid the existing observability profile's Grafana (`3000`) and Prometheus (`9090`) ports. The other component ports bind to `127.0.0.1`. Restrict public access to the UI and MinIO ports with the host firewall or 1Panel site configuration.

For an HTTPS 1Panel reverse proxy, set `NEXTAUTH_URL` to the public HTTPS URL and set `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT` to a browser-reachable MinIO endpoint. The main project's `LANGFUSE_HOST` can still use the server's LAN IP and published UI port.

## Upstream

The service images and data layout follow the [official Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose). Check the official instructions before upgrading major versions.
