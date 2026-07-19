FROM python:3.12-slim

# Same MkDocs stack the CI build uses (see .github/workflows/main.yml)
RUN pip install --no-cache-dir \
    mkdocs \
    mkdocs-material \
    mkdocs-nav-weight \
    mkdocs-gen-files

WORKDIR /userGuide

EXPOSE 8000

# Bind to 0.0.0.0 (not the default localhost) so the mapped port is reachable from the host
CMD ["mkdocs", "serve", "--dev-addr", "0.0.0.0:8000"]
