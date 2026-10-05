import { redirect } from "next/navigation";

/** The Entity Catalog is an admin governance tool in the Admin Center. */
export default function EntityCatalogPage() {
  redirect("/admin?tab=catalog");
}
