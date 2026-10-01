import { redirect } from "next/navigation";

/** LLM configuration and usage now live in the Admin Center (admin only). */
export default function LlmObservabilityPage() {
  redirect("/admin?tab=ai");
}
