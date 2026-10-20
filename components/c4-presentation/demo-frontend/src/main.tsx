import React from "react";
import ReactDOM from "react-dom/client";
import VersionRoute from "./guidance-v2/VersionRoute";
import "./styles.css";
import "./guidance/scaffolds.css";
import "./feedback/feedback.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <VersionRoute />
  </React.StrictMode>,
);
