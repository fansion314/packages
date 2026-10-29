/** Pure routing: all release and snapshot locations are embedded at deployment. */
export function createWorker(config) {
  const respond = (body, status = 200, extra = {}) => new Response(body, {
    status, headers: { "cache-control": "no-store", ...extra },
  });
  return {
    fetch(request) {
      if (!["GET", "HEAD"].includes(request.method)) {
        return respond("Method Not Allowed\n", 405, { allow: "GET, HEAD" });
      }
      const path = new URL(request.url).pathname;
      if (path === "/status.json" || (config.mirror && path === "/mirror/status.json")) {
        return respond(request.method === "HEAD" ? null : JSON.stringify({
          schema: 1, active: config.active, candidate: config.candidate,
          phase: config.phase, snapshots: config.snapshots, assets: Object.keys(config.assets).length,
          ...(config.mirror ? { mirror: config.mirror } : {}),
        }), 200, { "content-type": "application/json" });
      }
      if (path === "/") {
        return respond(request.method === "HEAD" ? null : config.instructions, 200,
          { "content-type": "text/plain; charset=utf-8" });
      }
      const target = Object.hasOwn(config.assets, path) ? config.assets[path] : undefined;
      if (!target) return respond("Not Found\n", 404);
      return respond(null, 302, { location: target });
    },
  };
}
