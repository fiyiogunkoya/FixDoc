import { NextResponse } from "next/server";

/** Unauthenticated healthcheck for Railway's edge probe. Middleware allows
 * /api/* through for webhooks; this is cheaper than hitting /sign-in. */
export function GET() {
  return NextResponse.json({ status: "ok" });
}

export const dynamic = "force-static";
