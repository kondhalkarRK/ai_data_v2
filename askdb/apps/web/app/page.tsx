import { redirect } from "next/navigation";

/** Data Preview is the landing tab; middleware handles the signed-out case. */
export default function RootPage() {
  redirect("/data-preview");
}
