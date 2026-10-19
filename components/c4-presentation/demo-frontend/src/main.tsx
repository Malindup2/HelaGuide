import React from "react";
import ReactDOM from "react-dom/client";
import InspectorRoute from "./inspector/InspectorRoute";
import "./styles.css";
import "./guidance/scaffolds.css";
import "./feedback/feedback.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <InspectorRoute />
  </React.StrictMode>,
);