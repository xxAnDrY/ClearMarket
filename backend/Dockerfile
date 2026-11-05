FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir .
RUN useradd --system clearmarket
USER clearmarket
ENV PYTHONPATH=/srv
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
