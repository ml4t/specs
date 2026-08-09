# Shared project context: ml4t-specs

## Package

- Package name: `ml4t-specs`
- Import path: `ml4t.specs`
- Purpose: runtime-neutral contracts shared by ML4T libraries

## Workflow

```bash
uv sync
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check
uv run pytest
```

## Contract requirements

- Keep specifications independent of engine implementations.
- Use versioned, serializable values for cross-library behavior.
- Export public contract types from `ml4t.specs`.
