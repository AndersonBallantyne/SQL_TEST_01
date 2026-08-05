FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/agent.py src/tools.py src/logging_utils.py src/app.py src/verify_answer.py ./src/

CMD ["python", "src/agent.py"]

