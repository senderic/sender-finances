FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY src/ src/
COPY config.yaml ./

RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

CMD [".venv/bin/streamlit", "run", "src/dashboard.py", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.address", "0.0.0.0"]
