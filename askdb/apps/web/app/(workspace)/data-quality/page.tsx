"use client";

import { TrustCenter } from "@/components/reliability/trust-center";
import { useActiveIndustry } from "@/hooks/use-session";

export default function DataTrustCenterPage() {
  const industry = useActiveIndustry();
  return (
    <div className="w-full animate-fade-in">
      <TrustCenter key={industry} industry={industry} />
    </div>
  );
}
