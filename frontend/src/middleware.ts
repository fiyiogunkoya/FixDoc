import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublic = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/webhooks(.*)",
  "/api/health",
]);

export default clerkMiddleware((auth, req) => {
  if (!isPublic(req)) {
    auth().protect();
  }
});

export const config = {
  matcher: [
    // Match everything except Next internals and static files
    "/((?!_next|.*\\..*).*)",
    "/",
    "/(api|trpc)(.*)",
  ],
};
