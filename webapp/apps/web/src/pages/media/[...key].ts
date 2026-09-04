// GET /media/[...key] — streams an object straight out of the R2 MEDIA
// binding (audio MP3s, visual PNGs). R2 egress is free, so this proxy costs
// nothing beyond the Worker request itself. Supports Range so <audio>
// playback and seeking within the buffered range work smoothly.
import type { APIRoute } from "astro";
import { env } from "cloudflare:workers";

export const GET: APIRoute = async ({ params, request }) => {
  const key = params.key;
  if (!key) {
    return new Response("not found", { status: 404 });
  }

  const bucket = env.MEDIA;
  const range = request.headers.get("range");

  const object = range
    ? await bucket.get(key, { range: parseRange(range) })
    : await bucket.get(key);

  if (!object) {
    return new Response("not found", { status: 404 });
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  headers.set("accept-ranges", "bytes");
  headers.set("cache-control", "public, max-age=31536000, immutable");

  const isRanged = "range" in object && object.range;
  if (isRanged) {
    const r = object.range as { offset: number; length: number };
    headers.set("content-range", `bytes ${r.offset}-${r.offset + r.length - 1}/${object.size}`);
    return new Response(object.body, { status: 206, headers });
  }

  return new Response(object.body, { status: 200, headers });
};

function parseRange(header: string): R2Range | undefined {
  const match = /bytes=(\d+)-(\d*)/.exec(header);
  if (!match) return undefined;
  const offset = Number(match[1]);
  const end = match[2] ? Number(match[2]) : undefined;
  return end !== undefined ? { offset, length: end - offset + 1 } : { offset };
}
