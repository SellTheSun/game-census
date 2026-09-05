ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock
COPY src /app/src
COPY tests /app/tests
COPY pyproject.toml /app/pyproject.toml
COPY LICENSE /app/LICENSE
COPY tools/dev.py /app/tools/dev.py
COPY build/toolchain.lock.json /app/build/toolchain.lock.json
ENTRYPOINT ["python", "-m", "game_census"]
