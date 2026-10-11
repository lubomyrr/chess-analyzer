FROM python:3.12-slim-bookworm AS stockfish-builder

ARG TARGETARCH
RUN mkdir -p /opt/stockfish \
    && if [ "$TARGETARCH" = "amd64" ]; then \
        apt-get update \
        && apt-get install --yes --no-install-recommends g++ make curl ca-certificates \
        && curl --fail --location --retry 3 \
            https://codeload.github.com/official-stockfish/Stockfish/tar.gz/758f9c9350abee36a5865ec701560db8ea62004d \
            --output /tmp/stockfish.tar.gz \
        && echo 'fd2e5f5506df5aa458b3d7113ecd0d9a8e2fe36d60c485dcc22f167e9214ab21  /tmp/stockfish.tar.gz' | sha256sum -c - \
        && mkdir /tmp/stockfish-src \
        && tar -xzf /tmp/stockfish.tar.gz -C /tmp/stockfish-src --strip-components=1 \
        && cd /tmp/stockfish-src/src \
        && if grep -qw avx2 /proc/cpuinfo && grep -qw bmi1 /proc/cpuinfo; then \
            make -j2 profile-build ARCH=x86-64-avx2 COMP=gcc; \
           else make -j2 build ARCH=x86-64-avx2 COMP=gcc; fi \
        && strip stockfish \
        && cp stockfish /opt/stockfish/stockfish-avx2; \
    fi

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

COPY --from=stockfish-builder /opt/stockfish/ /opt/stockfish/

COPY pyproject.toml ./

RUN mkdir --parents app \
    && touch app/__init__.py \
    && python -m pip install --no-cache-dir .

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --create-home appuser

USER appuser

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
