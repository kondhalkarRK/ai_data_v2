import { redirect } from "next/navigation";

/** Data Sources moved onto the Home page (Ask Me hero). */
export default function DataSourcesRedirectPage() {
  redirect("/home#data-sources");
}
