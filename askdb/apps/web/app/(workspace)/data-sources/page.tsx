import { redirect } from "next/navigation";

/** Data Sources moved onto the Home page (Ask DB hero rebrand). */
export default function DataSourcesRedirectPage() {
  redirect("/home#data-sources");
}
