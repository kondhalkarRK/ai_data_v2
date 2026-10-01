import { redirect } from "next/navigation";

/** Operator diagnostics moved to the Admin Center audit log (admin only). */
export default function SystemLogsPage() {
  redirect("/admin?tab=audit");
}
