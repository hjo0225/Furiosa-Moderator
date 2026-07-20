FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./api/

# Cloud Run 은 PORT 를 주입한다. 인터뷰는 LLM 왕복을 기다리므로 워커를 넉넉히 둔다.
ENV PORT=8080
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 2
