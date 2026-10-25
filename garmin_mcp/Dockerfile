FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastmcp httpx
COPY server.py /app/server.py
CMD ["python", "/app/server.py"]
