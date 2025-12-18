# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Overview

cvat-canvas3d is a TypeScript library for 3D annotation in CVAT. It provides a Three.js-based canvas for viewing, drawing, and editing 3D cuboid annotations on point cloud data.

## Build Commands

```bash
# Build the package (compiles TypeScript and bundles with webpack)
yarn run build

# Development build (no minification)
yarn run build --mode=development
```

The build outputs to `dist/` with the library exposed as `window.canvas3d`.

## Architecture

### MVC Pattern
The canvas follows an MVC architecture with observer pattern:

- **Model** (`canvas3dModel.ts`): Holds state (activeElement, objects, mode, configuration, drawData), handles mode transitions, notifies listeners of changes via `UpdateReasons`
- **View** (`canvas3dView.ts`): Three.js rendering, handles user input (mouse/keyboard), manages 4 synchronized viewports (perspective + 3 orthographic)
- **Controller** (`canvas3dController.ts`): Thin layer exposing model data to view

### Key Files

| File | Purpose |
|------|---------|
| `canvas3d.ts` | Main `Canvas3d` class - public API facade |
| `canvas3dModel.ts` | State management, mode enum, update reasons |
| `canvas3dView.ts` | Three.js scene setup, 4-viewport rendering, interaction handlers |
| `cuboid.ts` | `CuboidModel` class for 3D bounding boxes with meshes for each view |
| `master.ts` | Observer pattern implementation (subscribe/notify) |
| `consts.ts` | Constants (camera settings, colors, helper names) |

### Four-Viewport System
The canvas renders four synchronized views:
- **Perspective**: Main 3D view with orbit controls
- **Top**: Orthographic bird's-eye view (XY plane)
- **Side**: Orthographic side view (XZ plane)
- **Front**: Orthographic front view (YZ plane)

Each viewport has its own `THREE.WebGLRenderer`, scene, camera, and controls.

### Modes
The canvas operates in these modes (defined in `Mode` enum):
- `IDLE`: Default state, selection enabled
- `DRAW`: Creating new cuboid annotations
- `EDIT`: Modifying existing annotations (resize/rotate)
- `DRAG_CANVAS`: Panning the view
- `GROUP`, `MERGE`, `SPLIT`: Multi-object operations

### Dependencies
- **three**: 3D rendering engine
- **camera-controls**: Camera manipulation for Three.js
- **cvat-core**: Provides `ObjectState`, `Label`, `ShapeType` types

## Integration

The canvas is instantiated and controlled by cvat-ui:

```typescript
const canvas = new Canvas3d();

// Get HTML canvas elements for each viewport
const views = canvas.html(); // { perspective, top, side, front }

// Set up frame with point cloud and annotations
canvas.setup(frameData, objectStates);

// Activate annotation mode
canvas.draw({ enabled: true, shapeType: 'cuboid' });

// Select an object
canvas.activate(clientID);
```

## Keyboard Controls

Camera movement is handled via `CameraAction` enum keys:
- `I/K`: Zoom in/out
- `U/O`: Move up/down
- `J/L`: Move left/right
- Arrow keys: Tilt/rotate camera
