FROM python:3.12-slim
RUN pip install uv
WORKDIR /app
COPY . .
RUN uv pip install --system .
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT
