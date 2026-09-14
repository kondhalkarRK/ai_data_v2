import { redirect } from "next/navigation";

/** Home / hero is the landing experience. */
export default function RootPage() {
  redirect("/home");
}
