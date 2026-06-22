FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries=5 -r requirements.txt
COPY . .
EXPOSE 8005
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
