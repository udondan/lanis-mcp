FROM python:3.14-alpine AS builder

RUN apk add --no-cache gcc musl-dev

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.14-alpine

LABEL com.docker.desktop.mcp="true"
LABEL com.docker.desktop.mcp.name="lanis-mcp"

COPY --from=builder /install /usr/local

CMD ["lanis-mcp"]
