FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install \
	fastapi \
	uvicorn \
	psycopg2-binary \
	"langchain>=0.2,<0.3" \
	"langchain-core>=0.2,<0.3" \
	"langchain-openai>=0.1,<0.2" \
	"langchain-google-genai>=1,<2" \
	openai
COPY app ./app
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
