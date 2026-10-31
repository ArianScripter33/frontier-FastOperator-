FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config.py llm_client.py telemetry.py store.py vnc_client.py screen_agent.py service.py ./
ENV FRONTIER_STATE_DIR=/tmp/frontier-state
CMD ["python", "service.py"]
