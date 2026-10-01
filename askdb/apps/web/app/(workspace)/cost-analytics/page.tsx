import { redirect } from "next/navigation";

/** Cost Analytics moved into the Admin Center LLM usage view. */
export default function CostAnalyticsRedirectPage() {
  redirect("/admin?tab=usage");
}
