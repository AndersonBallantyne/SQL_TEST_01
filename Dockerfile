FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bakes the embedding model into the image at build time so no container ever hits the
# network for it at runtime. Without this, every fresh container's first search_summaries/
# search_docs call re-downloads the ~90MB model from HuggingFace Hub, measured at ~36s
# (vs. ~2.4s once cached) - see project memory, 2026-08-06 latency investigation.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY src/agent.py src/tools.py src/logging_utils.py src/app.py src/verify_answer.py ./src/
COPY .streamlit/config.toml ./.streamlit/config.toml

CMD ["python", "src/agent.py"]

