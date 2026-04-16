import { createStore } from "solid-js/store";
import type { Session, SnapshotInfo } from "../lib/tauri-bridge";

export interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  isLoading: boolean;
  snapshots: SnapshotInfo[];
}

const [sessionState, setSessionState] = createStore<SessionState>({
  sessions: [],
  activeSessionId: null,
  isLoading: false,
  snapshots: [],
});

export const setSessions = (sessions: Session[]) =>
  setSessionState("sessions", sessions);
export const setActiveSessionId = (id: string | null) =>
  setSessionState("activeSessionId", id);
export const setSessionLoading = (loading: boolean) =>
  setSessionState("isLoading", loading);
export const setSnapshots = (snapshots: SnapshotInfo[]) =>
  setSessionState("snapshots", snapshots);

export const addSnapshot = (snapshot: SnapshotInfo) => {
  setSessionState("snapshots", (prev) => [...prev, snapshot]);
};

export { sessionState };
