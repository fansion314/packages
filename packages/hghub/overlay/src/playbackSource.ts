import type { PlayInfo } from "./types";

/** Use the new full stream while retaining older mirror response compatibility. */
export function playbackSource(info: PlayInfo | null | undefined): string {
  const source = info?.streams?.main || info?.video_url;
  if (!source) throw new Error("暂无播放地址");
  return source;
}

/** Cancel delivery when Feed switches episode or unmounts; the request may finish. */
export function loadPlayback(
  request: () => Promise<PlayInfo>,
  onSource: (source: string) => void,
  onError: (error: Error) => void,
): () => void {
  let active = true;
  request()
    .then((info) => { if (active) onSource(playbackSource(info)); })
    .catch((error: Error) => { if (active) onError(error); });
  return () => { active = false; };
}
