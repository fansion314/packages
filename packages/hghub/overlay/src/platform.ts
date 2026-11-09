export type Platform = "android" | "ios" | "windows" | "macos" | "linux";

export function detectPlatform(userAgent: string, maxTouchPoints = 0): Platform {
  if (/Android/i.test(userAgent)) return "android";
  if (/iPhone|iPad|iPod/i.test(userAgent) || (/Macintosh/i.test(userAgent) && maxTouchPoints > 1)) return "ios";
  if (/Macintosh|Mac OS X/i.test(userAgent)) return "macos";
  return /Linux|X11/i.test(userAgent) ? "linux" : "windows";
}

export function mediaOrigin(platform: Platform): string {
  return platform === "windows" || platform === "android" ? "http://hg.localhost" : "hg://localhost";
}
