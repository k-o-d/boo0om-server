FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

ENV MUSIC_DIR=/music DATA_DIR=/data HOST=0.0.0.0 PORT=9813 PYTHONUNBUFFERED=1
EXPOSE 9813
VOLUME ["/data"]

CMD ["python", "server.py"]
