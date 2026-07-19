FROM python:3.12-slim

# ffmpeg: timelapse encoding · postgresql-client: pg_dump backups
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg postgresql-client \
 && rm -rf /var/lib/apt/lists/*

# The droplet has no global IPv6 route; without this, dual-stack hosts
# (googleapis, openai, github) sometimes get dialed on their AAAA address
# first → "Network is unreachable". Prefer IPv4-mapped addresses.
RUN printf 'precedence ::ffff:0:0/96 100\n' >> /etc/gai.conf

# Build context is cloud/ (see docker-compose.yml) so the dashboard can ride along.
WORKDIR /srv
COPY api/pyproject.toml ./
COPY api/app ./app
RUN pip install --no-cache-dir .

COPY dashboard ./dashboard

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
