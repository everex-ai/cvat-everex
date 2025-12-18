# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Overview

cvat-canvas is the 2D annotation canvas library for CVAT. It provides an SVG-based canvas for viewing, drawing, and editing annotations on images. This package is part of the CVAT yarn workspace and is consumed by cvat-ui.

## Build Commands

```bash
# Build the package (from this directory)
yarn run build
yarn run build --mode=development  # without minification

# Build from root workspace
yarn build:cvat-canvas

# Lint
yarn run eslint .
```

## Architecture

The canvas follows an **MVC pattern** with an observer-based notification system:

### Core Components

- **`canvas.ts`** - Public API entry point, creates and coordinates MVC components
- **`canvasModel.ts`** - State management (CanvasModelImpl), holds all canvas state including geometry, objects, drawing mode, configuration
- **`canvasController.ts`** - User input handling, mediates between view and model
- **`canvasView.ts`** - SVG rendering, DOM management, event dispatching
- **`master.ts`** - Observer pattern implementation (Master/Listener) for state change notifications

### Handler Classes

Each annotation mode has a dedicated handler:
- `drawHandler.ts` - Shape drawing (rectangle, polygon, polyline, points, ellipse, cuboid, skeleton, mask)
- `editHandler.ts` - Shape editing and point manipulation
- `mergeHandler.ts` - Merging multiple annotations
- `groupHandler.ts` - Grouping annotations
- `splitHandler.ts` - Splitting tracks
- `sliceHandler.ts` - Slicing masks/polygons
- `interactionHandler.ts` - AI-assisted annotation interactions
- `masksHandler.ts` - Brush/eraser tools for mask annotation
- `zoomHandler.ts` - Zoom region selection
- `autoborderHandler.ts` - Automatic border snapping

### Canvas Modes

The canvas operates in mutually exclusive modes defined in `canvasModel.ts`:
- IDLE, DRAW, EDIT, MERGE, SPLIT, GROUP, JOIN, SLICE, INTERACT, SELECT_REGION, DRAG_CANVAS, ZOOM_CANVAS, DRAG, RESIZE

### Key Dependencies

- **svg.js 2.7.1** - Core SVG manipulation library
- **svg.draw.js, svg.draggable.js, svg.select.js, svg.resize.js** - SVG interaction plugins
- **polylabel** - Finding pole of inaccessibility for label placement

### Output

Webpack bundles to `dist/cvat-canvas.[contenthash].js` with TypeScript declarations in `dist/declaration/`.

## CSS Classes and IDs

Shapes: `cvat_canvas_shape`, `cvat_canvas_shape_{clientID}`
States: `cvat_canvas_shape_activated`, `cvat_canvas_shape_drawing`, `cvat_canvas_shape_merging`, `cvat_canvas_shape_occluded`
Other: `cvat_canvas_image`, `cvat_canvas_grid`, `cvat_canvas_text`, `cvat_canvas_crosshair`

## Events

The canvas emits standard JS events on state changes. Key events:
- `canvas.setup`, `canvas.drawn`, `canvas.edited`, `canvas.activated`
- `canvas.merged`, `canvas.grouped`, `canvas.splitted`, `canvas.sliced`
- `canvas.zoom`, `canvas.fit`, `canvas.dragstart`, `canvas.dragstop`

See README.md for the complete event list and API reaction matrix.
