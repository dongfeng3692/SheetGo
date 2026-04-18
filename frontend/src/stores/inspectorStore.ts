import { createStore } from "solid-js/store";

interface InspectorState {
  parseInspectorOpen: boolean;
}

const [inspectorState, setInspectorState] = createStore<InspectorState>({
  parseInspectorOpen: false,
});

export const openParseInspector = () => setInspectorState("parseInspectorOpen", true);

export const closeParseInspector = () => setInspectorState("parseInspectorOpen", false);

export { inspectorState };
