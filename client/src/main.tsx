import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { BrandPreview } from "./components/BrandPreview";
import "./styles.css";

const el = document.getElementById("root");
if (!el) throw new Error("#root not found");

// ?preview=1 -> standalone brand/candle/reveal review (no worker needed).
const isPreview = new URLSearchParams(window.location.search).has("preview");

createRoot(el).render(
  <StrictMode>{isPreview ? <BrandPreview /> : <App />}</StrictMode>,
);
