import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { BrandPreview } from "./components/BrandPreview";
import { bootstrapPortalAccessFromUrl, consumeOAuthReturn } from "./lib/portalAccess";
import "./styles.css";

const el = document.getElementById("root");
if (!el) throw new Error("#root not found");

// Consume Google OAuth first, then retain legacy access links during migration.
consumeOAuthReturn();
bootstrapPortalAccessFromUrl();

// ?preview=1 -> standalone brand/candle/reveal review (no worker needed).
const isPreview = new URLSearchParams(window.location.search).has("preview");

createRoot(el).render(
  <StrictMode>{isPreview ? <BrandPreview /> : <App />}</StrictMode>,
);
