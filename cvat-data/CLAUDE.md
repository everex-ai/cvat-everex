# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Overview

`cvat-data` is a TypeScript library for decoding video chunks and image archives on the client side. It's the lowest-level frontend package in the CVAT workspace dependency chain (`cvat-data` <- `cvat-core` <- `cvat-canvas` <- `cvat-ui`).

## Build Commands

```bash
# Build for production (minified)
yarn run build

# Build for development (unminified)
yarn run build --mode=development

# Type checking
yarn run type-check

# Type checking in watch mode
yarn run type-check:watch
```

When working from the monorepo root:
```bash
yarn build:cvat-data
yarn workspace cvat-data run type-check
```

## Architecture

### Core Components

**FrameDecoder** (`src/ts/cvat-data.ts`) - Main class for decoding video/image chunks with:
- LRU caching of decoded chunks via `orderedStack`
- Mutex-based concurrency control for decode operations
- Request deduplication (ignores outdated requests via `RequestOutdatedError`)
- Two block types: `MP4VIDEO` (H.264 video) and `ARCHIVE` (zip of images)
- Two dimension types: `DIMENSION_2D` (returns ImageBitmap) and `DIMENSION_3D` (returns Blob)

**Workers:**
- `unzip_imgs.worker.ts` - Web Worker for extracting and decoding images from zip archives using JSZip
- `3rdparty/Decoder.worker.js` - Broadway.js H.264 decoder Web Worker

### Third-Party Dependencies

The `src/ts/3rdparty/` folder contains Broadway.js components for H.264 video decoding:
- `Decoder.worker.js` - H.264 decoder worker
- `mp4.js` - MP4 container parser
- `avc.wasm` - WebAssembly H.264 decoder

These are vendored because Broadway.js has no npm package. See `src/ts/3rdparty/README.md` for rebuild instructions.

## Key Patterns

### Chunk Decoding Flow
1. `requestDecodeBlock()` queues a decode request
2. `startDecode()` acquires mutex and processes based on block type
3. For video: Broadway.js worker decodes H.264 NAL units → `cropImage()` → `createImageBitmap()`
4. For archives: zip worker extracts files → `createImageBitmap()` (2D) or returns Blob (3D)
5. Results cached in `decodedChunks` with LRU eviction via `cleanup()`

### Thread Safety
All decode operations are serialized through an async mutex. Outdated requests are rejected with `RequestOutdatedError` rather than processed.

## Code Style

- TypeScript with ESLint (Airbnb config)
- 4-space indentation
- `src/ts/3rdparty/` is excluded from linting
