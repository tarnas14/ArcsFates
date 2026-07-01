This is a knowledge repository for [Arcs](https://boardgamegeek.com/boardgame/359871/arcs) and [Arcs: The Bligthed Reach Expansion](https://boardgamegeek.com/boardgameexpansion/363757/arcs-the-blighted-reach-expansion)

## Local development

Requires only Docker (no local Python). Builds and serves the `userGuide` docs with live reload:

```sh
docker compose up --build
```

Open http://localhost:3335 — edits to files under `userGuide/` reload the browser automatically.

Use a different host port with `MKDOCS_PORT`:

```sh
MKDOCS_PORT=4000 docker compose up
```

