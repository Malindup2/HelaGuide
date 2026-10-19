import { useEffect, useState } from "react";
import App from "../App";
import PipelineInspector from "./PipelineInspector";
import { isInspectorAddress } from "./controller";

/** Mount one application only: Inspector never mounts citizen workspace effects. */
export default function InspectorRoute() {
  const [inspecting, setInspecting] = useState(() => isInspectorAddress(window.location.hash));
  useEffect(() => {
    const changed = () => setInspecting(isInspectorAddress(window.location.hash));
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return inspecting ? <PipelineInspector /> : <App />;
}
