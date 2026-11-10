import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/base.css";
import "./styles/panels.css";

const root = document.getElementById("root");
if (!root) throw new Error("falta o elemento #root");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
