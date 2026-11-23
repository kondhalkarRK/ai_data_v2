import { redirect } from "next/navigation";

/** Data Sources moved onto the Home page (Soci hero). */
export default function DataSourcesRedirectPage() {
  redirect("/home#data-sources");
}
