import { NextResponse, type NextRequest } from "next/server";

/**
 * Coarse route protection.
 *
 * Presence is intentionally the only check here. FastAPI remains the authority on token
 * validity; copying the signing key into Next.js would create a second trust boundary.
 *
 * TEMPORARY: set NEXT_PUBLIC_AUTH_BYPASS=true (with API AUTH_BYPASS=true) to skip the
 * login gate while debugging local setup. Never enable in production builds.
 */
const REFRESH_COOKIE = "nql_refresh";
const PUBLIC_PATHS = ["/login"];
const AUTH_BYPASS = process.env.NEXT_PUBLIC_AUTH_BYPASS === "true";

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (AUTH_BYPASS) {
    if (pathname === "/login" || pathname.startsWith("/login/")) {
      const url = request.nextUrl.clone();
      url.pathname = "/data-preview";
      url.search = "";
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(REFRESH_COOKIE);
  const isPublic = PUBLIC_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  if (!hasSession && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  if (hasSession && isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/data-preview";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|brand/|.*\\.(?:svg|png|jpg|ico)$).*)"],
};
