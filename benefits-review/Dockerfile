FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY prompts/ ./prompts/
COPY data/catalog/ ./data/catalog/

EXPOSE 8088

CMD ["python", "-m", "src.main"]
