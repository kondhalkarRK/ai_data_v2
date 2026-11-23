/** Names come from /auth/me, never a demo account or a hardcoded fallback name. */
export function chatGreeting(fullName?: string | null): string {
  const first = fullName?.trim().split(/\s+/)[0];
  return first ? `Hi, ${first}` : "Hi there.";
}
