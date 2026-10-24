// CI-only adapter: exercise the actual generated Worker with pacman before
// selecting its snapshot on the production Worker.
import { createServer } from "node:http";
import worker from "./generated/index.mjs";

const server = createServer(async (request, response) => {
  try {
    const result = await worker.fetch(new Request(`http://localhost${request.url}`, { method: request.method }));
    response.writeHead(result.status, Object.fromEntries(result.headers));
    response.end(Buffer.from(await result.arrayBuffer()));
  } catch (error) {
    console.error(error);
    response.writeHead(500);
    response.end();
  }
});
server.listen(8765, "127.0.0.1", () => console.log("Candidate Worker listening on 8765"));
