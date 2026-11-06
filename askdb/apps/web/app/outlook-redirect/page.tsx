"use client";

import * as React from "react";
import { broadcastResponseToMainFrame } from "@azure/msal-browser/redirect-bridge";

export default function OutlookRedirect() {
  React.useEffect(() => { void broadcastResponseToMainFrame(); }, []);
  return <p>Completing Outlook sign-in…</p>;
}
