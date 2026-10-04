FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr ffmpeg libglib2.0-0 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY public ./public
EXPOSE 10000
CMD ["sh","-c","uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
