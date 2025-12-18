# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cvat-cli is the command-line client for CVAT (Computer Vision Annotation Tool). It provides CLI access to CVAT server operations for tasks, projects, and serverless functions. The CLI depends on cvat-sdk for API client functionality.

## Build and Development Commands

```bash
# Install in editable mode for development
pip install -e .

# Install test dependencies
pip install -r requirements/testing.txt

# Run unit tests (from parent cvat/ directory)
cd ../
python manage.py test --settings cvat.settings.testing cvat-cli/
```

## Code Style

- Black formatter with 100 char line length
- isort for import sorting (profile: black)
- Target Python 3.10+

## Architecture

### Entry Point
- `src/cvat_cli/__main__.py` - Main entry point, configures argument parser and dispatches to commands

### Command System (`src/cvat_cli/_internal/`)
- `command_base.py` - Base classes for commands:
  - `Command` protocol - interface all commands implement
  - `CommandGroup` - groups related commands (e.g., all task commands)
  - `GenericListCommand`, `GenericDeleteCommand` - reusable command implementations
  - `DeprecatedAlias` - wraps commands with deprecation warnings
- `commands_all.py` - Root command group, aggregates all resource command groups
- `commands_tasks.py` - Task operations (create, delete, ls, frames, export-dataset, import-dataset, backup, auto-annotate)
- `commands_projects.py` - Project operations (create, delete, ls)
- `commands_functions.py` - Function operations (create-native, delete, run-agent) - Enterprise/Cloud only
- `common.py` - Shared utilities: authentication handling, client building, function loading
- `agent.py` - Agent implementation for processing native function requests (detection/tracking)
- `parsers.py` - Argument parsing utilities
- `utils.py` - General utilities

### Key Patterns

**Command Registration**: Commands are registered via decorators on CommandGroup instances:
```python
@COMMANDS.command_class("create")
class TaskCreate:
    description = "..."
    def configure_parser(self, parser): ...
    def execute(self, client, **kwargs): ...
```

**Authentication**: Supports three methods:
1. `CVAT_ACCESS_TOKEN` environment variable (Personal Access Token)
2. `--auth USER:PASS` argument
3. Interactive password prompt (defaults to current system user)

**Function Loading**: Auto-annotation functions can be loaded from:
- Python modules (`--function-module`)
- Python files (`--function-file`)

**Agent System**: The agent (`agent.py`) processes annotation requests for native functions using a multiprocess architecture with `_RecoverableExecutor` for fault tolerance.

### Dependencies
- `cvat-sdk` - CVAT Python SDK for API access
- `attrs` - Data classes
- `Pillow` - Image handling for auto-annotation
