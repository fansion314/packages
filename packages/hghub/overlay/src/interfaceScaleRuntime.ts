import { useSyncExternalStore } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { platform } from "./api";
import { createInterfaceScale, INTERFACE_SCALE_KEY, scaleShortcut } from "./interfaceScale";

export const interfaceScale = createInterfaceScale({
  setZoom: (factor) => getCurrentWebview().setZoom(factor),
  read: () => localStorage.getItem(INTERFACE_SCALE_KEY),
  write: (value) => localStorage.setItem(INTERFACE_SCALE_KEY, value),
});

export function useInterfaceScale() {
  return useSyncExternalStore(interfaceScale.subscribe, interfaceScale.getSnapshot);
}

let initialization: Promise<void> | undefined;
export function initializeInterfaceScale(): Promise<void> {
  if (platform !== "linux") return Promise.resolve();
  if (!initialization) {
    // Tauri zoomHotkeysEnabled stays disabled; one handler owns native zoom and persistence.
    window.addEventListener("keydown", (event) => {
      const direction = scaleShortcut(event);
      if (direction === null) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      void interfaceScale.step(direction);
    }, true);
    initialization = interfaceScale.initialize();
  }
  return initialization;
}
