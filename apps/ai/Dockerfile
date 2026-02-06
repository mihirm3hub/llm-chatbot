FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install fastapi uvicorn langchain openai psycopg2-binary
COPY app ./app
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
