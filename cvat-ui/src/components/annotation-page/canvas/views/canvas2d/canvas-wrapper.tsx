// Copyright (C) 2020-2022 Intel Corporation
// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

import './styles.scss';

import React from 'react';
import { connect } from 'react-redux';
import Slider from 'antd/lib/slider';
import Spin from 'antd/lib/spin';
import Popover from 'antd/lib/popover';
import { PlusCircleOutlined, UpOutlined } from '@ant-design/icons';
import notification from 'antd/lib/notification';
import debounce from 'lodash/debounce';

import GlobalHotKeys, { KeyMap } from 'utils/mousetrap-react';
import {
    ColorBy, GridColor, Workspace, ActiveControl, CombinedState,
} from 'reducers';
import { EventScope } from 'cvat-logger';
import { Canvas, HighlightSeverity, CanvasHint } from 'cvat-canvas-wrapper';
import {
    AnnotationConflict, ObjectState, ObjectType, ShapeType, QualityConflict, getCore,
} from 'cvat-core-wrapper';
import config from 'config';
import CVATTooltip from 'components/common/cvat-tooltip';
import FrameTags from 'components/annotation-page/tag-annotation-workspace/frame-tags';
import {
    confirmCanvasReadyAsync,
    resetCanvas,
    updateActiveControl as updateActiveControlAction,
    updateAnnotationsAsync,
    updateMultipleAnnotationsAsync,
    createAnnotationsAsync,
    mergeAnnotationsAsync,
    groupAnnotationsAsync,
    joinAnnotationsAsync,
    sliceAnnotationsAsync,
    splitAnnotationsAsync,
    activateObject,
    selectObjects as selectObjectsAction,
    toggleObjectSelection as toggleObjectSelectionAction,
    updateCanvasContextMenu,
    addZLayer,
    switchZLayer,
    fetchAnnotationsAsync,
    getDataFailed,
    canvasErrorOccurred,
    updateEditedStateAsync,
} from 'actions/annotation-actions';
import {
    switchGrid,
    changeGridColor,
    changeGridOpacity,
    changeBrightnessLevel,
    changeContrastLevel,
    changeSaturationLevel,
    switchAutomaticBordering,
} from 'actions/settings-actions';
import { reviewActions } from 'actions/review-actions';

import { filterAnnotations } from 'utils/filter-annotations';
import { ImageFilter } from 'utils/image-processing';
import { ShortcutScope } from 'utils/enums';
import { registerComponentShortcuts } from 'actions/shortcuts-actions';
import { subKeyMap } from 'utils/component-subkeymap';
import ImageSetupsContent from './image-setups-content';
import CanvasTipsComponent from './canvas-hints';

const cvat = getCore();
const MAX_DISTANCE_TO_OPEN_SHAPE = 50;

interface StateToProps {
    canvasInstance: Canvas | null;
    jobInstance: any;
    activatedStateID: number | null;
    activatedElementID: number | null;
    activatedAttributeID: number | null;
    annotations: ObjectState[];
    frameData: any;
    frameAngle: number;
    canvasIsReady: boolean;
    frame: number;
    opacity: number;
    colorBy: ColorBy;
    selectedOpacity: number;
    outlined: boolean;
    outlineColor: string;
    showBitmap: boolean;
    showProjections: boolean;
    grid: boolean;
    gridSize: number;
    gridColor: GridColor;
    gridOpacity: number;
    activeLabelID: number;
    activeObjectType: ObjectType;
    brightnessLevel: number;
    contrastLevel: number;
    saturationLevel: number;
    resetZoom: boolean;
    smoothImage: boolean;
    focusedObjectPadding: number;
    showObjectsTextAlways: boolean;
    textFontSize: number;
    controlPointsSize: number;
    textPosition: 'auto' | 'center';
    textContent: string;
    showAllInterpolationTracks: boolean;
    workspace: Workspace;
    minZLayer: number;
    maxZLayer: number;
    curZLayer: number;
    automaticBordering: boolean;
    adaptiveZoom: boolean;
    intelligentPolygonCrop: boolean;
    switchableAutomaticBordering: boolean;
    keyMap: KeyMap;
    showTagsOnFrame: boolean;
    conflicts: QualityConflict[];
    showGroundTruth: boolean;
    highlightedConflict: QualityConflict | null;
    imageFilters: ImageFilter[];
    selectedStatesID: number[];
    activeControl: ActiveControl;
    activeObjectHidden: boolean;
}

interface DispatchToProps {
    onSetupCanvas(): void;
    onResetCanvas: () => void;
    updateActiveControl: (activeControl: ActiveControl) => void;
    onUpdateAnnotations(states: ObjectState[]): void;
    onCreateAnnotations(states: ObjectState[]): void;
    onMergeAnnotations(states: ObjectState[]): void;
    onSplitAnnotations(state: ObjectState): void;
    onGroupAnnotations(states: ObjectState[]): void;
    onJoinAnnotations(states: ObjectState[], points: number[]): void;
    onSliceAnnotations(state: ObjectState, results: number[][]): void;
    onActivateObject: (activatedStateID: number | null, activatedElementID: number | null) => void;
    onAddZLayer(): void;
    onSwitchZLayer(cur: number): void;
    onChangeBrightnessLevel(level: number): void;
    onChangeContrastLevel(level: number): void;
    onChangeSaturationLevel(level: number): void;
    onChangeGridOpacity(opacity: number): void;
    onChangeGridColor(color: GridColor): void;
    onSwitchGrid(enabled: boolean): void;
    onSwitchAutomaticBordering(enabled: boolean): void;
    onFetchAnnotation(): void;
    onGetDataFailed(error: Error): void;
    onCanvasErrorOccurred(error: Error): void;
    onStartIssue(position: number[]): void;
    onUpdateEditedObject(editedState: ObjectState | null): void;
    onToggleObjectSelection(stateID: number): void;
    onSelectObjects(stateIDs: number[]): void;
    onUpdateMultipleAnnotations(statesToUpdate: any[]): void;
}

function mapStateToProps(state: CombinedState): StateToProps {
    const {
        annotation: {
            canvas: {
                activeControl, instance: canvasInstance, ready: canvasIsReady, activeObjectHidden,
            },
            drawing: { activeLabelID, activeObjectType },
            job: { instance: jobInstance },
            player: {
                frame: { data: frameData, number: frame },
                frameAngles,
            },
            annotations: {
                states: annotations,
                activatedStateID,
                activatedElementID,
                activatedAttributeID,
                selectedStatesID,
                zLayer: { cur: curZLayer, min: minZLayer, max: maxZLayer },
                highlightedConflict,
            },
            workspace,
        },
        settings: {
            player: {
                grid,
                gridSize,
                gridColor,
                gridOpacity,
                brightnessLevel,
                contrastLevel,
                saturationLevel,
                resetZoom,
                smoothImage,
            },
            workspace: {
                focusedObjectPadding,
                showObjectsTextAlways,
                showAllInterpolationTracks,
                showTagsOnFrame,
                automaticBordering,
                adaptiveZoom,
                intelligentPolygonCrop,
                textFontSize,
                controlPointsSize,
                textPosition,
                textContent,
            },
            shapes: {
                opacity, colorBy, selectedOpacity, outlined, outlineColor, showBitmap, showProjections, showGroundTruth,
            },
            imageFilters,
        },
        shortcuts: { keyMap },
        review: { conflicts },
    } = state;

    return {
        canvasInstance,
        jobInstance,
        frameData,
        frameAngle: frameAngles[frame - jobInstance.startFrame],
        canvasIsReady,
        frame,
        activatedStateID,
        activatedElementID,
        activatedAttributeID,
        annotations,
        opacity: opacity / 100,
        colorBy,
        selectedOpacity: selectedOpacity / 100,
        outlined,
        outlineColor,
        showBitmap,
        showProjections,
        grid,
        gridSize,
        gridColor,
        gridOpacity: gridOpacity / 100,
        activeLabelID,
        activeObjectType,
        brightnessLevel: brightnessLevel / 100,
        contrastLevel: contrastLevel / 100,
        saturationLevel: saturationLevel / 100,
        resetZoom,
        smoothImage,
        focusedObjectPadding,
        showObjectsTextAlways,
        textFontSize,
        controlPointsSize,
        textPosition,
        textContent,
        showAllInterpolationTracks,
        showTagsOnFrame,
        curZLayer,
        minZLayer,
        maxZLayer,
        automaticBordering,
        adaptiveZoom,
        intelligentPolygonCrop,
        workspace,
        keyMap,
        activeControl,
        switchableAutomaticBordering:
            activeControl === ActiveControl.DRAW_POLYGON ||
            activeControl === ActiveControl.DRAW_POLYLINE ||
            activeControl === ActiveControl.DRAW_MASK ||
            activeControl === ActiveControl.EDIT,
        conflicts,
        showGroundTruth,
        highlightedConflict,
        selectedStatesID,
        imageFilters,
        activeObjectHidden,
    };
}

const componentShortcuts = {
    SWITCH_AUTOMATIC_BORDERING: {
        name: 'Switch automatic bordering',
        description: 'Switch automatic bordering for polygons and polylines during drawing/editing',
        sequences: ['ctrl+a'],
        scope: ShortcutScope.STANDARD_WORKSPACE,
    },
};

registerComponentShortcuts(componentShortcuts);

function mapDispatchToProps(dispatch: any): DispatchToProps {
    return {
        onSetupCanvas(): void {
            dispatch(confirmCanvasReadyAsync());
        },
        onResetCanvas(): void {
            dispatch(resetCanvas());
        },
        updateActiveControl(activeControl: ActiveControl): void {
            dispatch(updateActiveControlAction(activeControl));
        },
        onUpdateAnnotations(states: ObjectState[]): void {
            dispatch(updateAnnotationsAsync(states));
        },
        onCreateAnnotations(states: ObjectState[]): void {
            dispatch(createAnnotationsAsync(states));
        },
        onMergeAnnotations(states: ObjectState[]): void {
            dispatch(mergeAnnotationsAsync(states));
        },
        onGroupAnnotations(states: ObjectState[]): void {
            dispatch(groupAnnotationsAsync(states));
        },
        onJoinAnnotations(states: ObjectState[], points: number[]): void {
            dispatch(joinAnnotationsAsync(states, points));
        },
        onSliceAnnotations(state: ObjectState, results: number[][]): void {
            dispatch(sliceAnnotationsAsync(state, results));
        },
        onSplitAnnotations(state: ObjectState): void {
            dispatch(splitAnnotationsAsync(state));
        },
        onActivateObject(activatedStateID: number | null, activatedElementID: number | null = null): void {
            if (activatedStateID === null) {
                dispatch(updateCanvasContextMenu(false, 0, 0));
            }

            dispatch(activateObject(activatedStateID, activatedElementID, null));
        },
        onAddZLayer(): void {
            dispatch(addZLayer());
        },
        onSwitchZLayer(cur: number): void {
            dispatch(switchZLayer(cur));
        },
        onChangeBrightnessLevel(level: number): void {
            dispatch(changeBrightnessLevel(level));
        },
        onChangeContrastLevel(level: number): void {
            dispatch(changeContrastLevel(level));
        },
        onChangeSaturationLevel(level: number): void {
            dispatch(changeSaturationLevel(level));
        },
        onChangeGridOpacity(opacity: number): void {
            dispatch(changeGridOpacity(opacity));
        },
        onChangeGridColor(color: GridColor): void {
            dispatch(changeGridColor(color));
        },
        onSwitchGrid(enabled: boolean): void {
            dispatch(switchGrid(enabled));
        },
        onSwitchAutomaticBordering(enabled: boolean): void {
            dispatch(switchAutomaticBordering(enabled));
        },
        onFetchAnnotation(): void {
            dispatch(fetchAnnotationsAsync());
        },
        onGetDataFailed(error: Error): void {
            dispatch(getDataFailed(error));
        },
        onCanvasErrorOccurred(error: Error): void {
            dispatch(canvasErrorOccurred(error));
        },
        onStartIssue(position: number[]): void {
            dispatch(reviewActions.startIssue(position));
        },
        onUpdateEditedObject(editedState: ObjectState | null): void {
            dispatch(updateEditedStateAsync(editedState));
        },
        onToggleObjectSelection(stateID: number): void {
            dispatch(toggleObjectSelectionAction(stateID));
        },
        onSelectObjects(stateIDs: number[]): void {
            dispatch(selectObjectsAction(stateIDs));
        },
        onUpdateMultipleAnnotations(statesToUpdate: any[]): void {
            dispatch(updateMultipleAnnotationsAsync(statesToUpdate));
        },
    };
}

type Props = StateToProps & DispatchToProps;

class CanvasWrapperComponent extends React.PureComponent<Props> {
    private debouncedUpdate = debounce(this.updateCanvas.bind(this), 250, { leading: true });
    private canvasTipsRef = React.createRef<CanvasTipsComponent>();
    private shiftClickStart: { x: number; y: number } | null = null;

    public componentDidMount(): void {
        const {
            automaticBordering,
            adaptiveZoom,
            intelligentPolygonCrop,
            showObjectsTextAlways,
            workspace,
            showProjections,
            selectedOpacity,
            opacity,
            smoothImage,
            textFontSize,
            controlPointsSize,
            textPosition,
            textContent,
            colorBy,
            outlined,
            outlineColor,
            showGroundTruth,
            resetZoom,
            focusedObjectPadding,
        } = this.props;
        const { canvasInstance } = this.props as { canvasInstance: Canvas };

        // It's awful approach from the point of view React
        // But we do not have another way because cvat-canvas returns regular DOM element
        const [wrapper] = window.document.getElementsByClassName('cvat-canvas-container');
        wrapper.appendChild(canvasInstance.html());

        canvasInstance.configure({
            forceDisableEditing: workspace === Workspace.REVIEW,
            undefinedAttrValue: config.UNDEFINED_ATTRIBUTE_VALUE,
            displayAllText: showObjectsTextAlways,
            autoborders: automaticBordering,
            adaptiveZoom,
            showProjections,
            showConflicts: showGroundTruth,
            intelligentPolygonCrop,
            selectedShapeOpacity: selectedOpacity,
            controlPointsSize,
            shapeOpacity: opacity,
            smoothImage,
            colorBy,
            outlinedBorders: outlined ? outlineColor || 'black' : false,
            textFontSize,
            textPosition,
            textContent,
            resetZoom,
            focusedObjectPadding,
        });

        this.initialSetup();
        this.updateCanvas();
    }

    public componentDidUpdate(prevProps: Props): void {
        const {
            opacity,
            selectedOpacity,
            outlined,
            outlineColor,
            showBitmap,
            frameData,
            frameAngle,
            annotations,
            activatedStateID,
            curZLayer,
            resetZoom,
            smoothImage,
            grid,
            gridSize,
            gridOpacity,
            gridColor,
            brightnessLevel,
            contrastLevel,
            saturationLevel,
            workspace,
            showObjectsTextAlways,
            textFontSize,
            controlPointsSize,
            textPosition,
            textContent,
            showAllInterpolationTracks,
            automaticBordering,
            adaptiveZoom,
            intelligentPolygonCrop,
            showProjections,
            colorBy,
            onFetchAnnotation,
            showGroundTruth,
            highlightedConflict,
            imageFilters,
            focusedObjectPadding,
        } = this.props;
        const { canvasInstance } = this.props as { canvasInstance: Canvas };

        if (
            prevProps.showObjectsTextAlways !== showObjectsTextAlways ||
            prevProps.automaticBordering !== automaticBordering ||
            prevProps.adaptiveZoom !== adaptiveZoom ||
            prevProps.showProjections !== showProjections ||
            prevProps.intelligentPolygonCrop !== intelligentPolygonCrop ||
            prevProps.opacity !== opacity ||
            prevProps.selectedOpacity !== selectedOpacity ||
            prevProps.smoothImage !== smoothImage ||
            prevProps.textFontSize !== textFontSize ||
            prevProps.controlPointsSize !== controlPointsSize ||
            prevProps.textPosition !== textPosition ||
            prevProps.textContent !== textContent ||
            prevProps.colorBy !== colorBy ||
            prevProps.outlineColor !== outlineColor ||
            prevProps.outlined !== outlined ||
            prevProps.showGroundTruth !== showGroundTruth ||
            prevProps.resetZoom !== resetZoom ||
            prevProps.focusedObjectPadding !== focusedObjectPadding
        ) {
            canvasInstance.configure({
                undefinedAttrValue: config.UNDEFINED_ATTRIBUTE_VALUE,
                displayAllText: showObjectsTextAlways,
                autoborders: automaticBordering,
                adaptiveZoom,
                showProjections,
                intelligentPolygonCrop,
                selectedShapeOpacity: selectedOpacity,
                shapeOpacity: opacity,
                smoothImage,
                colorBy,
                outlinedBorders: outlined ? outlineColor || 'black' : false,
                textFontSize,
                controlPointsSize,
                textPosition,
                textContent,
                showConflicts: showGroundTruth,
                resetZoom,
                focusedObjectPadding,
            });
        }

        if (prevProps.showAllInterpolationTracks !== showAllInterpolationTracks) {
            onFetchAnnotation();
        }

        if (prevProps.activatedStateID !== null && prevProps.activatedStateID !== activatedStateID) {
            canvasInstance.activate(null);
        }

        if (prevProps.highlightedConflict !== highlightedConflict) {
            const severity: HighlightSeverity | undefined = highlightedConflict
                ?.severity as unknown as HighlightSeverity;

            const highlightedObjects = (highlightedConflict?.annotationConflicts || [])
                .map((conflict: AnnotationConflict) => annotations
                    .find((state) => state.serverID === conflict.serverID && state.objectType === conflict.type),
                ).filter((state: ObjectState | undefined) => !!state) as ObjectState[];
            const highlightedClientIDs = highlightedObjects.map((state) => state?.clientID) as number[];

            const highlightedTags = highlightedObjects.some((state) => state?.objectType === ObjectType.TAG);
            if (highlightedTags && prevProps.highlightedConflict) {
                canvasInstance.highlight([], null);
            } else if (!highlightedTags) {
                canvasInstance.highlight(highlightedClientIDs, severity || null);
            }
        }

        if (gridSize !== prevProps.gridSize) {
            canvasInstance.grid(gridSize, gridSize);
        }

        if (gridOpacity !== prevProps.gridOpacity || gridColor !== prevProps.gridColor || grid !== prevProps.grid) {
            const gridElement = window.document.getElementById('cvat_canvas_grid');
            const gridPattern = window.document.getElementById('cvat_canvas_grid_pattern');
            if (gridElement) {
                gridElement.style.display = grid ? 'block' : 'none';
            }
            if (gridPattern) {
                gridPattern.style.stroke = gridColor.toLowerCase();
                gridPattern.style.opacity = `${gridOpacity}`;
            }
        }

        if (
            brightnessLevel !== prevProps.brightnessLevel ||
            contrastLevel !== prevProps.contrastLevel ||
            saturationLevel !== prevProps.saturationLevel
        ) {
            canvasInstance.configure({
                CSSImageFilter:
                    `brightness(${brightnessLevel}) contrast(${contrastLevel}) saturate(${saturationLevel})`,
            });
        }

        if (prevProps.imageFilters !== imageFilters) {
            canvasInstance.configure({ forceFrameUpdate: true });
        }

        if (
            prevProps.annotations !== annotations ||
            prevProps.frameData !== frameData ||
            prevProps.curZLayer !== curZLayer
        ) {
            this.updateCanvas();
        } else if (prevProps.imageFilters !== imageFilters) {
            // In case of frequent image filters changes, we apply debounced canvas update
            // that makes UI smoother
            this.debouncedUpdate();
        }

        if (prevProps.showBitmap !== showBitmap) {
            canvasInstance.bitmap(showBitmap);
        }

        if (prevProps.frameAngle !== frameAngle) {
            canvasInstance.rotate(frameAngle);
            if (prevProps.frameData === frameData) {
                // explicitly rotated, not a new frame
                canvasInstance.fit();
            }
        }

        if (prevProps.workspace !== workspace) {
            if (workspace === Workspace.REVIEW) {
                canvasInstance.configure({
                    forceDisableEditing: true,
                });
            } else if (prevProps.workspace === Workspace.REVIEW) {
                canvasInstance.configure({
                    forceDisableEditing: false,
                });
            }
        }

        const { selectedStatesID } = this.props;
        if (prevProps.selectedStatesID !== selectedStatesID) {
            canvasInstance.setSelection(selectedStatesID);
        }

        this.activateOnCanvas();
    }

    public componentWillUnmount(): void {
        const { canvasInstance } = this.props as { canvasInstance: Canvas };

        canvasInstance.html().removeEventListener('mousedown', this.onCanvasMouseDown);
        canvasInstance.html().removeEventListener('mouseup', this.onCanvasMouseUp as EventListener);
        canvasInstance.html().removeEventListener('click', this.onCanvasClicked);
        canvasInstance.html().removeEventListener('canvas.editstart', this.onCanvasEditStart);
        canvasInstance.html().removeEventListener('canvas.edited', this.onCanvasEditDone);
        canvasInstance.html().removeEventListener('canvas.sliced', this.onCanvasSliceDone);
        canvasInstance.html().removeEventListener('canvas.dragstart', this.onCanvasDragStart);
        canvasInstance.html().removeEventListener('canvas.dragstop', this.onCanvasDragDone);
        canvasInstance.html().removeEventListener('canvas.zoomstart', this.onCanvasZoomStart);
        canvasInstance.html().removeEventListener('canvas.zoomstop', this.onCanvasZoomDone);

        canvasInstance.html().removeEventListener('canvas.setup', this.onCanvasSetup);
        canvasInstance.html().removeEventListener('canvas.canceled', this.onCanvasCancel);
        canvasInstance.html().removeEventListener('canvas.find', this.onCanvasFindObject);
        canvasInstance.html().removeEventListener('canvas.deactivated', this.onCanvasShapeDeactivated);
        canvasInstance.html().removeEventListener('canvas.moved', this.onCanvasCursorMoved);

        canvasInstance.html().removeEventListener('canvas.zoom', this.onCanvasZoomChanged);
        canvasInstance.html().removeEventListener('canvas.fit', this.onCanvasImageFitted);
        canvasInstance.html().removeEventListener('canvas.dragshape', this.onCanvasShapeDragged as EventListener);
        canvasInstance.html().removeEventListener('canvas.resizeshape', this.onCanvasShapeResized as EventListener);
        canvasInstance.html().removeEventListener('canvas.clicked', this.onCanvasShapeClicked);
        canvasInstance.html().removeEventListener('canvas.drawn', this.onCanvasShapeDrawn);
        canvasInstance.html().removeEventListener('canvas.merged', this.onCanvasObjectsMerged);
        canvasInstance.html().removeEventListener('canvas.grouped', this.onCanvasObjectsGrouped);
        canvasInstance.html().removeEventListener('canvas.joined', this.onCanvasObjectsJoined);
        canvasInstance.html().removeEventListener('canvas.regionselected', this.onCanvasPositionSelected);
        canvasInstance.html().removeEventListener('canvas.splitted', this.onCanvasTrackSplitted);

        canvasInstance.html().removeEventListener('canvas.multiedited', this.onCanvasMultiEdited);
        canvasInstance.html().removeEventListener('canvas.multiselected', this.onCanvasMultiSelected);

        canvasInstance.html().removeEventListener('canvas.error', this.onCanvasErrorOccurrence);
        canvasInstance.html().removeEventListener('canvas.message', this.onCanvasMessage as EventListener);
    }

    private onCanvasErrorOccurrence = (event: any): void => {
        const { exception, domain } = event.detail;
        if (domain === 'data fetching') {
            const { onGetDataFailed } = this.props;
            onGetDataFailed(exception);
        } else {
            const { onCanvasErrorOccurred } = this.props;
            onCanvasErrorOccurred(exception);
        }
    };

    private onCanvasMessage = (event: CustomEvent<{ messages: CanvasHint[] | null, topic: string }>): void => {
        const { messages, topic } = event.detail;
        this.canvasTipsRef.current?.update(messages, topic);
    };

    private onCanvasShapeDrawn = (event: any): void => {
        const {
            jobInstance, activeLabelID, activeObjectType, frame, updateActiveControl, onCreateAnnotations,
            onUpdateEditedObject, activeObjectHidden, workspace,
        } = this.props;

        if (!event.detail.continue) {
            updateActiveControl(ActiveControl.CURSOR);
        }

        const { duration } = event.detail;

        // Multi-paste: event.detail.states is an array
        if (event.detail.states) {
            const objectStates = event.detail.states.map((s: any) => {
                s.frame = frame;
                s.objectType = s.objectType ?? activeObjectType;
                s.label = s.label || jobInstance.labels
                    .filter((label: any) => label.id === activeLabelID)[0];
                s.rotation = s.rotation || 0;
                s.occluded = s.occluded || false;
                s.outside = s.outside || false;
                s.hidden = s.hidden || (activeObjectHidden && workspace !== Workspace.SINGLE_SHAPE);
                if (s.shapeType === ShapeType.SKELETON && Array.isArray(s.elements)) {
                    s.elements.forEach((element: Record<string, any>) => {
                        element.objectType = s.objectType;
                        element.label = element.label || s.label.structure
                            .sublabels.find((label: any) => label.id === element.labelID);
                        element.frame = frame;
                        element.rotation = 0;
                        element.occluded = element.occluded || false;
                        element.outside = element.outside || false;
                    });
                }
                return new cvat.classes.ObjectState(s);
            });

            jobInstance.logger.log(EventScope.pasteObject, { count: objectStates.length, duration });
            onCreateAnnotations(objectStates);
            onUpdateEditedObject(null);
            return;
        }

        // Single shape draw/paste
        const { state } = event.detail;
        const isDrawnFromScratch = !state.label;

        state.objectType = state.shapeType === ShapeType.MASK ?
            ObjectType.SHAPE : state.objectType ?? activeObjectType;
        state.label = state.label || jobInstance.labels.filter((label: any) => label.id === activeLabelID)[0];
        state.frame = frame;
        state.rotation = state.rotation || 0;
        state.occluded = state.occluded || false;
        state.outside = state.outside || false;
        state.hidden = state.hidden || (activeObjectHidden && workspace !== Workspace.SINGLE_SHAPE);
        if (state.shapeType === ShapeType.SKELETON && Array.isArray(state.elements)) {
            state.elements.forEach((element: Record<string, any>) => {
                element.objectType = state.objectType;
                element.label = element.label || state.label.structure
                    .sublabels.find((label: any) => label.id === element.labelID);
                element.frame = state.frame;
                element.rotation = 0;
                element.occluded = element.occluded || false;
                element.outside = element.outside || false;
            });
        }

        if (isDrawnFromScratch) {
            jobInstance.logger.log(EventScope.drawObject, { count: 1, duration });
        } else {
            jobInstance.logger.log(EventScope.pasteObject, { count: 1, duration });
        }

        const objectState = new cvat.classes.ObjectState(state);
        onCreateAnnotations([objectState]);
        onUpdateEditedObject(null);
    };

    private onCanvasObjectsMerged = (event: any): void => {
        const {
            jobInstance, onMergeAnnotations, updateActiveControl,
        } = this.props;

        updateActiveControl(ActiveControl.CURSOR);
        const { states, duration } = event.detail;
        jobInstance.logger.log(EventScope.mergeObjects, {
            duration,
            count: states.length,
        });
        onMergeAnnotations(states);
    };

    private onCanvasObjectsGrouped = (event: any): void => {
        const {
            jobInstance, onGroupAnnotations, updateActiveControl,
        } = this.props;

        updateActiveControl(ActiveControl.CURSOR);
        const { states, duration } = event.detail;
        jobInstance.logger.log(EventScope.groupObjects, {
            duration,
            count: states.length,
        });
        onGroupAnnotations(states);
    };

    private onCanvasObjectsJoined = (event: any): void => {
        const {
            jobInstance, onJoinAnnotations, updateActiveControl,
        } = this.props;

        updateActiveControl(ActiveControl.CURSOR);
        const { states, points, duration } = event.detail;
        jobInstance.logger.log(EventScope.joinObjects, {
            duration,
            count: states.length,
        });
        onJoinAnnotations(states, points);
    };

    private onCanvasTrackSplitted = (event: any): void => {
        const {
            jobInstance, onSplitAnnotations, updateActiveControl,
        } = this.props;

        updateActiveControl(ActiveControl.CURSOR);
        const { state, duration } = event.detail;
        jobInstance.logger.log(EventScope.splitObjects, {
            duration,
            count: 1,
        });
        onSplitAnnotations(state);
    };

    private onCanvasPositionSelected = (event: any): void => {
        const { onStartIssue } = this.props;
        const { points } = event.detail;
        onStartIssue(points);
    };

    private onCanvasMouseDown = (e: MouseEvent): void => {
        const {
            workspace, activatedStateID, onActivateObject, onSelectObjects, selectedStatesID,
        } = this.props;

        if ((e.target as HTMLElement).tagName === 'svg' && e.button !== 2) {
            if (!e.shiftKey && selectedStatesID.length > 0) {
                onSelectObjects([]);
            }
            if (activatedStateID !== null && workspace !== Workspace.ATTRIBUTES) {
                onActivateObject(null, null);
            }
        }

        // Track Shift+mousedown position for Shift+Click selection
        if (e.shiftKey && e.button === 0) {
            this.shiftClickStart = { x: e.clientX, y: e.clientY };
        }
    };

    private onCanvasMouseUp = (e: MouseEvent): void => {
        if (!this.shiftClickStart || !e.shiftKey || e.button !== 0) {
            this.shiftClickStart = null;
            return;
        }

        // Only handle as click if mouse didn't move much (not a drag)
        const dist = Math.sqrt(
            (e.clientX - this.shiftClickStart.x) ** 2 + (e.clientY - this.shiftClickStart.y) ** 2,
        );
        this.shiftClickStart = null;
        if (dist > 5) return;

        const { onToggleObjectSelection, annotations } = this.props;

        // Use elementFromPoint to find the shape under cursor
        const target = document.elementFromPoint(e.clientX, e.clientY);
        if (!target) return;

        const shapeEl = (target as Element).closest('[data-z-order]');
        if (!shapeEl) return;

        const idMatch = shapeEl.id?.match(/^cvat_canvas_shape_(\d+)$/);
        if (!idMatch) return;

        const clickedClientID = parseInt(idMatch[1], 10);

        // Find the top-level state (for skeleton elements, use parentID)
        const clickedState = annotations.find((s: any) => s.clientID === clickedClientID);
        if (clickedState) {
            onToggleObjectSelection(clickedClientID);
        } else {
            // It might be a skeleton element, find parent
            for (const ann of annotations) {
                if (ann.elements?.some((el: any) => el.clientID === clickedClientID)) {
                    onToggleObjectSelection(ann.clientID);
                    break;
                }
            }
        }
    };

    private onCanvasClicked = (): void => {
        const { canvasInstance } = this.props as { canvasInstance: Canvas };
        if (!canvasInstance.html().contains(document.activeElement) && document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }
    };

    private onCanvasShapeDragged = (e: CustomEvent<{ duration: number; state: ObjectState }>): void => {
        const { jobInstance } = this.props;
        const { detail: { duration, state: { serverID } } } = e;
        jobInstance.logger.log(
            EventScope.dragObject,
            { duration, ...(serverID ? { obj_id: serverID } : {}) },
        );
    };

    private onCanvasShapeResized = (e: CustomEvent<{ duration: number; state: ObjectState }>): void => {
        const { jobInstance } = this.props;
        const { detail: { duration, state: { serverID } } } = e;

        jobInstance.logger.log(
            EventScope.resizeObject,
            { duration, ...(serverID ? { obj_id: serverID } : {}) },
        );
    };

    private onCanvasImageFitted = (): void => {
        const { jobInstance } = this.props;
        jobInstance.logger.log(EventScope.fitImage);
    };

    private onCanvasZoomChanged = (): void => {
        const { jobInstance } = this.props;
        jobInstance.logger.log(EventScope.zoomImage);
    };

    private onCanvasShapeClicked = (e: any): void => {
        const { clientID, parentID } = e.detail.state;
        const { shiftKey } = e.detail;

        // Shift+Click selection is handled by onCanvasMouseUp to avoid double-toggle
        if (shiftKey) {
            return;
        }

        let sidebarItem = null;
        if (Number.isInteger(parentID)) {
            sidebarItem = window.document.getElementById(`cvat-objects-sidebar-state-item-element-${clientID}`);
        } else {
            sidebarItem = window.document.getElementById(`cvat-objects-sidebar-state-item-${clientID}`);
        }

        if (sidebarItem) {
            sidebarItem.scrollIntoView();
        }
    };

    private onCanvasMultiEdited = (event: any): void => {
        const { onUpdateMultipleAnnotations } = this.props;
        const { edits } = event.detail;
        const statesToUpdate = edits.map((edit: { state: any; points: number[]; bbox?: number[] }) => {
            const updatedState = edit.state;
            updatedState.points = edit.points;
            // Skeletons carry the translated wrapping bbox so it moves with the
            // keypoints instead of expanding to cover the old + new positions.
            if (updatedState.shapeType === 'skeleton' && Array.isArray(edit.bbox) && edit.bbox.length === 4) {
                updatedState.bbox = edit.bbox;
            }
            return updatedState;
        });
        onUpdateMultipleAnnotations(statesToUpdate);
    };

    private onCanvasMultiSelected = (event: any): void => {
        const { onSelectObjects } = this.props;
        const { clientIDs } = event.detail;
        onSelectObjects(clientIDs);
    };

    private onCanvasShapeDeactivated = (e: any): void => {
        const { onActivateObject, activatedStateID } = this.props;
        const { state } = e.detail;

        // when we activate element, canvas deactivates the previous
        // and triggers this event
        // in this case we do not need to update our state
        if (state.clientID === activatedStateID) {
            onActivateObject(null, null);
        }
    };

    private onCanvasCursorMoved = async (event: any): Promise<void> => {
        const {
            jobInstance, activatedStateID, activatedElementID, workspace, onActivateObject,
        } = this.props;

        if (![Workspace.STANDARD, Workspace.REVIEW, Workspace.SINGLE_SHAPE].includes(workspace)) {
            return;
        }

        // When Shift is held, don't auto-activate objects (user is selecting)
        if (event.detail.shiftKey) {
            return;
        }

        const result = await jobInstance.annotations.select(event.detail.states, event.detail.x, event.detail.y);
        if (result && result.state) {
            if ([ShapeType.POLYLINE, ShapeType.POINTS].includes(result.state.shapeType)) {
                if (result.distance > MAX_DISTANCE_TO_OPEN_SHAPE) {
                    return;
                }
            }

            const newActivatedElement = event.detail.activatedElementID || null;
            if (activatedStateID !== result.state.clientID || activatedElementID !== newActivatedElement) {
                onActivateObject(result.state.clientID, event.detail.activatedElementID || null);
            }
        }
    };

    private onCanvasEditStart = (event: any): void => {
        const { updateActiveControl, onUpdateEditedObject } = this.props;
        updateActiveControl(ActiveControl.EDIT);
        onUpdateEditedObject(event.detail.state);
    };

    private onCanvasEditDone = (event: any): void => {
        const {
            activeControl, onUpdateAnnotations, updateActiveControl, onUpdateEditedObject,
            annotations,
        } = this.props;
        const {
            state, points, rotation, bbox,
        } = event.detail;
        // Skeleton edits can carry an optional bbox alongside points/rotation.
        // The canvas signals: rotation handle => rotation update; corner/edge
        // resize on a skeleton => bbox-only; line drag or keypoint move =>
        // points (and the bbox that translated or soft-snapped with them).
        if (state.shapeType === 'skeleton' && Array.isArray(bbox) && bbox.length === 4) {
            state.bbox = bbox;
        }
        if (state.rotation !== rotation) {
            state.rotation = rotation;
        } else if (Array.isArray(points) && points.length > 0) {
            state.points = points;
        }

        if (activeControl !== ActiveControl.CURSOR) {
            // do not need to reset and deactivate if it was just resizing/dragging and other simple actions
            updateActiveControl(ActiveControl.CURSOR);
        }
        // Skeleton keypoint edits arrive with the element's ObjectState.
        // The edit is forwarded onto the matching child inside the PARENT
        // state and only the parent is dispatched: SkeletonShape/SkeletonTrack
        // .save apply the child update and the soft-snapped bbox together as
        // ONE history entry, so a single undo restores keypoints and bbox at
        // once. Saving the child separately would both duplicate the change
        // and split the action into several undo steps.
        let statesToUpdate: any[] = [state];
        if (Number.isInteger(state.parentID) && Array.isArray(annotations)) {
            const parentState = annotations.find(
                (s: any) => s.clientID === state.parentID,
            );
            if (parentState && parentState.shapeType === 'skeleton' &&
                Array.isArray(points) && points.length > 0 &&
                Array.isArray(parentState.elements)) {
                const childInParent = parentState.elements.find(
                    (el: any) => el.clientID === state.clientID,
                );
                if (childInParent) {
                    childInParent.points = points;
                    statesToUpdate = [parentState];
                }
            }
        }
        onUpdateAnnotations(statesToUpdate);
        onUpdateEditedObject(null);
    };

    private onCanvasSliceDone = (event: any): void => {
        const { jobInstance, updateActiveControl, onSliceAnnotations } = this.props;
        const { state, results, duration } = event.detail;
        updateActiveControl(ActiveControl.CURSOR);
        jobInstance.logger.log(EventScope.sliceObject, {
            count: 1,
            duration,
        });
        onSliceAnnotations(state, results);
    };
    private onCanvasDragStart = (): void => {
        const { updateActiveControl } = this.props;
        updateActiveControl(ActiveControl.DRAG_CANVAS);
    };

    private onCanvasDragDone = (): void => {
        const { updateActiveControl } = this.props;
        updateActiveControl(ActiveControl.CURSOR);
    };

    private onCanvasZoomStart = (): void => {
        const { updateActiveControl } = this.props;
        updateActiveControl(ActiveControl.ZOOM_CANVAS);
    };

    private onCanvasZoomDone = (): void => {
        const { updateActiveControl } = this.props;
        updateActiveControl(ActiveControl.CURSOR);
    };

    private onCanvasSetup = (): void => {
        const { onSetupCanvas } = this.props;
        onSetupCanvas();
        this.activateOnCanvas();
    };

    private onCanvasCancel = (): void => {
        const { onResetCanvas, onUpdateEditedObject } = this.props;
        onResetCanvas();
        onUpdateEditedObject(null);
    };

    private onCanvasFindObject = async (e: any): Promise<void> => {
        const { jobInstance } = this.props;
        const { canvasInstance } = this.props as { canvasInstance: Canvas };

        const result = await jobInstance.annotations.select(e.detail.states, e.detail.x, e.detail.y);

        if (result && result.state) {
            if (['polyline', 'points'].includes(result.state.shapeType)) {
                if (result.distance > MAX_DISTANCE_TO_OPEN_SHAPE) {
                    return;
                }
            }

            canvasInstance.select(result.state);
        }
    };

    private activateOnCanvas(): void {
        const {
            activatedStateID,
            activatedAttributeID,
            workspace,
            annotations,
        } = this.props;
        const { canvasInstance } = this.props as { canvasInstance: Canvas };

        if (activatedStateID !== null) {
            const [activatedState] = annotations.filter((state: any): boolean => state.clientID === activatedStateID);
            if (activatedState && workspace === Workspace.ATTRIBUTES) {
                if (activatedState.objectType !== ObjectType.TAG) {
                    canvasInstance.focus(activatedStateID);
                } else {
                    canvasInstance.fit();
                }
            }
            if (activatedState && activatedState.objectType !== ObjectType.TAG) {
                canvasInstance.activate(activatedStateID, activatedAttributeID);
            }
        } else if (workspace === Workspace.ATTRIBUTES) {
            canvasInstance.fit();
        }
    }

    private updateCanvas(): void {
        const {
            curZLayer, annotations, frameData,
            workspace, frame, imageFilters,
        } = this.props;

        const { canvasInstance } = this.props as { canvasInstance: Canvas };
        if (frameData !== null && canvasInstance) {
            const filteredAnnotations = filterAnnotations(annotations, {
                frame,
                workspace,
                exclude: [ObjectType.TAG],
            });
            const proxy = new Proxy(frameData, {
                get: (_frameData, prop, receiver) => {
                    if (prop === 'data') {
                        return async (...args: any[]) => {
                            const originalImage = await _frameData.data(...args);
                            const imageIsNotProcessed = imageFilters.some((imageFilter: ImageFilter) => (
                                imageFilter.modifier.currentProcessedImage !== frame
                            ));

                            if (imageIsNotProcessed) {
                                try {
                                    const { renderWidth, renderHeight, imageData: imageBitmap } = originalImage;

                                    const offscreen = new OffscreenCanvas(renderWidth, renderHeight);
                                    const ctx = offscreen.getContext('2d') as OffscreenCanvasRenderingContext2D;
                                    ctx.drawImage(imageBitmap, 0, 0, renderWidth, renderHeight);
                                    const imageData = ctx.getImageData(0, 0, renderWidth, renderHeight);

                                    const newImageData = imageFilters
                                        .reduce((oldImageData, activeImageModifier) => activeImageModifier
                                            .modifier.processImage(oldImageData, frame), imageData);
                                    const newImageBitmap = await createImageBitmap(newImageData);
                                    return {
                                        renderWidth,
                                        renderHeight,
                                        imageData: newImageBitmap,
                                    };
                                } catch (error: any) {
                                    notification.error({
                                        description: error.toString(),
                                        message: 'Image processing error occurred',
                                        className: 'cvat-notification-notice-image-processing-error',
                                    });
                                }
                            }

                            return originalImage;
                        };
                    }
                    return Reflect.get(_frameData, prop, receiver);
                },
            });
            canvasInstance.setup(
                proxy,
                frameData.deleted ? [] : filteredAnnotations,
                curZLayer,
            );
            canvasInstance.configure({ forceFrameUpdate: false });
        }
    }

    private initialSetup(): void {
        const {
            grid,
            gridSize,
            gridColor,
            gridOpacity,
            brightnessLevel,
            contrastLevel,
            saturationLevel,
        } = this.props;
        const { canvasInstance } = this.props as { canvasInstance: Canvas };

        // Grid
        const gridElement = window.document.getElementById('cvat_canvas_grid');
        const gridPattern = window.document.getElementById('cvat_canvas_grid_pattern');
        if (gridElement) {
            gridElement.style.display = grid ? 'block' : 'none';
        }
        if (gridPattern) {
            gridPattern.style.stroke = gridColor.toLowerCase();
            gridPattern.style.opacity = `${gridOpacity}`;
        }
        canvasInstance.grid(gridSize, gridSize);

        canvasInstance.configure({
            CSSImageFilter:
                `brightness(${brightnessLevel}) contrast(${contrastLevel}) saturate(${saturationLevel})`,
        });

        canvasInstance.fitCanvas();
        canvasInstance.html().addEventListener(
            'canvas.setup',
            () => {
                const { activatedStateID, activatedAttributeID } = this.props;
                canvasInstance.activate(activatedStateID, activatedAttributeID);
            },
            { once: true },
        );

        canvasInstance.html().addEventListener('mousedown', this.onCanvasMouseDown);
        canvasInstance.html().addEventListener('mouseup', this.onCanvasMouseUp as EventListener);
        canvasInstance.html().addEventListener('click', this.onCanvasClicked);
        canvasInstance.html().addEventListener('canvas.editstart', this.onCanvasEditStart);
        canvasInstance.html().addEventListener('canvas.edited', this.onCanvasEditDone);
        canvasInstance.html().addEventListener('canvas.sliced', this.onCanvasSliceDone);
        canvasInstance.html().addEventListener('canvas.dragstart', this.onCanvasDragStart);
        canvasInstance.html().addEventListener('canvas.dragstop', this.onCanvasDragDone);
        canvasInstance.html().addEventListener('canvas.zoomstart', this.onCanvasZoomStart);
        canvasInstance.html().addEventListener('canvas.zoomstop', this.onCanvasZoomDone);

        canvasInstance.html().addEventListener('canvas.setup', this.onCanvasSetup);
        canvasInstance.html().addEventListener('canvas.canceled', this.onCanvasCancel);
        canvasInstance.html().addEventListener('canvas.find', this.onCanvasFindObject);
        canvasInstance.html().addEventListener('canvas.deactivated', this.onCanvasShapeDeactivated);
        canvasInstance.html().addEventListener('canvas.moved', this.onCanvasCursorMoved);

        canvasInstance.html().addEventListener('canvas.zoom', this.onCanvasZoomChanged);
        canvasInstance.html().addEventListener('canvas.fit', this.onCanvasImageFitted);
        canvasInstance.html().addEventListener('canvas.dragshape', this.onCanvasShapeDragged as EventListener);
        canvasInstance.html().addEventListener('canvas.resizeshape', this.onCanvasShapeResized as EventListener);
        canvasInstance.html().addEventListener('canvas.clicked', this.onCanvasShapeClicked);
        canvasInstance.html().addEventListener('canvas.drawn', this.onCanvasShapeDrawn);
        canvasInstance.html().addEventListener('canvas.merged', this.onCanvasObjectsMerged);
        canvasInstance.html().addEventListener('canvas.grouped', this.onCanvasObjectsGrouped);
        canvasInstance.html().addEventListener('canvas.joined', this.onCanvasObjectsJoined);
        canvasInstance.html().addEventListener('canvas.regionselected', this.onCanvasPositionSelected);
        canvasInstance.html().addEventListener('canvas.splitted', this.onCanvasTrackSplitted);

        canvasInstance.html().addEventListener('canvas.multiedited', this.onCanvasMultiEdited);
        canvasInstance.html().addEventListener('canvas.multiselected', this.onCanvasMultiSelected);

        canvasInstance.html().addEventListener('canvas.error', this.onCanvasErrorOccurrence);
        canvasInstance.html().addEventListener('canvas.message', this.onCanvasMessage as EventListener);
    }

    public render(): JSX.Element {
        const {
            maxZLayer,
            curZLayer,
            minZLayer,
            keyMap,
            switchableAutomaticBordering,
            automaticBordering,
            showTagsOnFrame,
            canvasIsReady,
            onSwitchAutomaticBordering,
            onSwitchZLayer,
            onAddZLayer,
        } = this.props;

        const preventDefault = (event: KeyboardEvent | undefined): void => {
            if (event) {
                event.preventDefault();
            }
        };

        const handlers: Record<keyof typeof componentShortcuts, (event?: KeyboardEvent) => void> = {
            SWITCH_AUTOMATIC_BORDERING: (event: KeyboardEvent | undefined) => {
                if (switchableAutomaticBordering) {
                    preventDefault(event);
                    onSwitchAutomaticBordering(!automaticBordering);
                }
            },
        };

        return (
            <>
                <GlobalHotKeys keyMap={subKeyMap(componentShortcuts, keyMap)} handlers={handlers} />
                <CanvasTipsComponent ref={this.canvasTipsRef} />
                {
                    !canvasIsReady && (
                        <div className='cvat-spinner-container'>
                            <Spin className='cvat-spinner' />
                        </div>
                    )
                }

                {/*
                    This element doesn't have any props
                    So, React isn't going to rerender it
                    And it's a reason why cvat-canvas appended in mount function works
                */}
                <div
                    className='cvat-canvas-container'
                    style={{
                        overflow: 'hidden',
                        width: '100%',
                        height: '100%',
                    }}
                />

                <Popover
                    destroyTooltipOnHide
                    trigger='click'
                    placement='top'
                    overlayInnerStyle={{ padding: 0 }}
                    content={<ImageSetupsContent />}
                >
                    <UpOutlined className='cvat-canvas-image-setups-trigger' />
                </Popover>

                <div className='cvat-canvas-z-axis-wrapper'>
                    <Slider
                        disabled={minZLayer === maxZLayer}
                        min={minZLayer}
                        max={maxZLayer}
                        value={curZLayer}
                        vertical
                        reverse
                        defaultValue={0}
                        onChange={(value: number): void => onSwitchZLayer(value as number)}
                    />
                    <CVATTooltip title={`Add new layer ${maxZLayer + 1} and switch to it`}>
                        <PlusCircleOutlined onClick={onAddZLayer} />
                    </CVATTooltip>
                </div>

                {showTagsOnFrame ? (
                    <div className='cvat-canvas-frame-tags'>
                        <FrameTags />
                    </div>
                ) : null}
            </>
        );
    }
}

export default connect(mapStateToProps, mapDispatchToProps)(CanvasWrapperComponent);
