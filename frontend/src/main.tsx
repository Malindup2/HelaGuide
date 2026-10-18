import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./styles/fonts.css";
import "./index.css";
import { getInitialTheme, applyTheme, getInitialContrast, applyContrast } from "./lib/theme";
import App from "./App";

// Apply the (light, by default) theme before first paint so there is no flash.
applyTheme(getInitialTheme());
applyContrast(getInitialContrast());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
