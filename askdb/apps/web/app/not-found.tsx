import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <Logo size="lg" />
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        That route does not exist. It may have been renamed during the move from the
        previous application.
      </p>
      <Button asChild>
        <Link href="/home">Back to Home</Link>
      </Button>
    </main>
  );
}
