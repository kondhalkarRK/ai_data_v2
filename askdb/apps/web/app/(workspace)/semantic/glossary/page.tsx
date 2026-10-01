import { redirect } from "next/navigation";

export default function GlossaryPage() {
  redirect("/semantic?tab=model");
}
