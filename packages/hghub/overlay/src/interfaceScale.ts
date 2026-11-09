export const INTERFACE_SCALES = [75, 90, 100, 110, 125, 150, 175, 200] as const;
export const INTERFACE_SCALE_KEY = "hghub_interface_scale";
export type ScaleSnapshot = Readonly<{ value: number; pending: boolean; error: string | null }>;

type ScaleHost = {
  setZoom: (factor: number) => Promise<void>;
  read: () => string | null;
  write: (value: string) => void;
};

export function validScale(value: number): boolean {
  return (INTERFACE_SCALES as readonly number[]).includes(value);
}

export function scaleShortcut(event: Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "metaKey" | "altKey" | "isComposing">): -1 | 0 | 1 | null {
  if (!event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return null;
  if (event.key === "+" || event.key === "=" || event.code === "NumpadAdd") return 1;
  if (event.key === "-" || event.code === "NumpadSubtract") return -1;
  if (event.key === "0" || event.code === "Numpad0") return 0;
  return null;
}

/** Serialize requests so a slow native call cannot overwrite a later selection. */
export function createInterfaceScale(host: ScaleHost) {
  let snapshot: ScaleSnapshot = { value: 100, pending: false, error: null };
  let queue = Promise.resolve();
  let pending = 0;
  let initialization: Promise<void> | undefined;
  const listeners = new Set<() => void>();
  const publish = (update: Partial<ScaleSnapshot>) => {
    snapshot = { ...snapshot, ...update };
    for (const listener of listeners) listener();
  };
  const enqueue = (choose: () => number) => {
    pending++;
    publish({ pending: true, error: null });
    const operation = queue.then(async () => {
      const value = choose();
      if (!validScale(value)) {
        publish({ error: "不支持的界面缩放比例" });
        return;
      }
      try {
        await host.setZoom(value / 100);
      } catch {
        publish({ error: "界面缩放失败，已保持上次成功的比例，请重试" });
        return;
      }
      publish({ value, error: null });
      try { host.write(String(value)); }
      catch { publish({ error: "缩放已生效，但无法保存设置；重启后可能恢复默认" }); }
    }).finally(() => {
      pending--;
      publish({ pending: pending > 0 });
    });
    queue = operation;
    return operation;
  };
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    initialize() {
      if (!initialization) {
        let value = 100;
        try {
          const stored = host.read();
          const candidate = stored === null ? 100 : Number(stored);
          if (validScale(candidate)) value = candidate;
        } catch { /* A disabled or damaged store keeps the interface accessible. */ }
        initialization = enqueue(() => value);
      }
      return initialization;
    },
    set: (value: number) => enqueue(() => value),
    step: (direction: -1 | 0 | 1) => enqueue(() => {
      if (!direction) return 100;
      const index = (INTERFACE_SCALES as readonly number[]).indexOf(snapshot.value);
      return INTERFACE_SCALES[Math.max(0, Math.min(INTERFACE_SCALES.length - 1, index + direction))];
    }),
  };
}
