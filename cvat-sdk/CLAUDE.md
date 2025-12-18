# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

The CVAT SDK is a Python client library for the CVAT server. It provides multiple abstraction layers:

- **API Layer** (`cvat_sdk.api_client`) - Low-level OpenAPI-generated wrappers
- **Core Layer** (`cvat_sdk.core`) - High-level `Client` and proxy classes
- **Auto-Annotation** (`cvat_sdk.auto_annotation`) - Framework for automated annotation
- **PyTorch Adapter** (`cvat_sdk.pytorch`) - PyTorch Dataset wrappers
- **Utilities** (`cvat_sdk.attributes`, `cvat_sdk.masks`) - Specialized helpers

## Development Commands

### Installation
```bash
# Basic installation
pip install -e ./cvat-sdk

# With optional dependencies
pip install -e './cvat-sdk[masks]'      # numpy>=2 for mask utilities
pip install -e './cvat-sdk[pytorch]'    # torch, torchvision, scikit-image
```

### SDK Code Generation
The `api_client/` package is auto-generated from the CVAT OpenAPI schema:
```bash
# Install generation dependencies
pip install -r cvat-sdk/gen/requirements.txt

# Generate SDK (requires Docker, uses OpenAPI Generator v6.0.1)
./cvat-sdk/gen/generate.sh
```

Generation workflow:
1. Reads schema from `../cvat/schema.yml`
2. Generates `cvat_sdk/api_client/` via OpenAPI Generator
3. Runs `gen/postprocess.py` for code cleanup and modernization
4. Generates `cvat_sdk/version.py`

### Testing
```bash
# Install test dependencies
pip install -r tests/python/requirements.txt -e './cvat-sdk[masks,pytorch]'

# Run all SDK tests
pytest tests/python/sdk/

# Run specific test file
pytest tests/python/sdk/test_tasks.py

# Run tests matching pattern
pytest tests/python/sdk/ -k "test_can_login"
```

Tests require a running CVAT server instance.

## Architecture

### Package Structure
```
cvat_sdk/
├── api_client/        # Auto-generated OpenAPI wrappers (DO NOT EDIT MANUALLY)
├── core/
│   ├── client.py      # Client, Config, make_client(), credentials
│   ├── proxies/       # Domain proxies: TasksRepo, ProjectsRepo, JobsRepo, etc.
│   ├── downloading.py # Resumable downloads with progress
│   ├── uploading.py   # TUS protocol for resumable uploads
│   └── progress.py    # Progress tracking utilities
├── auto_annotation/
│   ├── driver.py      # annotate_task() main execution
│   ├── interface.py   # DetectionFunction, DetectionFunctionSpec
│   └── functions/     # Built-in torchvision implementations
├── pytorch/           # TaskVisionDataset, ProjectVisionDataset
├── datasets/          # Dataset export/import utilities
├── attributes.py      # Attribute handling
├── masks.py           # Mask utilities (requires masks extra)
└── models.py          # Re-export of API models
```

### Key Patterns

**Client Usage:**
```python
from cvat_sdk import make_client

with make_client(host="localhost", port=8080, credentials=("user", "pass")) as client:
    tasks = client.tasks.list()
    task = client.tasks.retrieve(task_id)
```

**Proxy Pattern:** Domain-specific repos (`client.tasks`, `client.projects`, `client.jobs`) provide CRUD operations wrapping the low-level API.

**Auto-Annotation:** Implement `DetectionFunction` interface, then call `annotate_task()` to apply predictions.

### Protected Files
Files listed in `.openapi-generator-ignore` are NOT overwritten during generation:
- `cvat_sdk/__init__.py`, `core/`, `auto_annotation/`, `pytorch/`, `datasets/`
- `gen/`, `requirements/base.txt`, `pyproject.toml`, `README.md`

## Code Style

- Black formatter: 100 char line length
- isort: black profile, `cvat_sdk` as first-party
- Target Python 3.10+
- PEP 604 syntax for Optional/Union types (`X | None` not `Optional[X]`)
