# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Overview

`cvat-core` is the client-side JavaScript/TypeScript API library for CVAT (Computer Vision Annotation Tool). It provides the business logic, data models, and server communication layer used by the frontend UI and other clients.

This package is part of a yarn workspaces monorepo. See the parent directory's CLAUDE.md for full project context.

## Build Commands

```bash
# Install dependencies (from repo root)
yarn --immutable

# Build the library
yarn run build
yarn run build --mode=development  # without minification

# Type checking
yarn run type-check
yarn run type-check:watch

# Lint (from repo root)
yarn run eslint cvat-core/
```

## Architecture

### Entry Points
- `src/api.ts` - Main entry point, builds and exports the CVATCore object
- `src/index.ts` - TypeScript interface definitions for the CVATCore API

### Key Architectural Patterns

**Plugin System** (`src/plugins.ts`):
All API methods are wrapped through `PluginRegistry.apiWrapper()` which enables plugins to intercept calls with `enter`/`leave` hooks. Plugins can prevent method execution or modify return values.

**Server Communication** (`src/server-proxy.ts`):
Central HTTP client using Axios with:
- TUS protocol for resumable file uploads
- Organization context injection via `enableOrganization()`
- Pagination helper `fetchAll()` for listing endpoints

**Session Classes** (`src/session.ts`, `src/session-implementation.ts`):
- `Task` and `Job` are the primary work units
- Implementation split pattern: `session.ts` defines class structure, `session-implementation.ts` adds method implementations via `implementTask()`/`implementJob()`
- Both share annotation methods via `buildDuplicatedAPI()` prototype injection

**Annotations System**:
- `src/annotations-objects.ts` - Shape, Track, Tag classes with interpolation logic
- `src/annotations-collection.ts` - Collection management for all annotation objects
- `src/annotations-saver.ts` - Handles saving annotations with change tracking
- `src/object-state.ts` - Immutable state representation for UI consumption

**Annotations Actions** (`src/annotations-actions/`):
Extensible action system for batch operations on annotations:
- `BaseAction` - Abstract base for all actions
- `BaseShapesAction` - For operations on individual shapes
- `BaseCollectionAction` - For operations on annotation collections

### Core Data Models
- `Project` / `Task` / `Job` - Work hierarchy
- `Label` / `Attribute` - Annotation schema
- `ObjectState` - Annotation state for shapes/tracks/tags
- `FrameData` / `FramesMetaData` - Frame and video metadata

### Enums (`src/enums.ts`)
All constants for shape types, job states, object types, etc. Always use these enums rather than string literals.

## Dependencies

- `cvat-data` - Linked sibling package for video frame parsing
- `axios` - HTTP client
- `tus-js-client` - Resumable uploads
- `lodash` - Utilities (used selectively)

## Code Patterns

- Methods return Promises; use async/await
- Classes are typically frozen after construction (`Object.freeze()`)
- Server response types in `src/server-response-types.ts`
- Request types in `src/server-request-types.ts`
- Exceptions are defined in `src/exceptions.ts` (ArgumentError, ServerError, DataError, ScriptingError)
