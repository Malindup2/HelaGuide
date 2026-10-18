import { Routes, Route } from "react-router-dom";
import Home from "./pages/Home";

/** Root routes. Only Home exists so far -- the conversation flow, guided
 * mode, and the rest of the citizen-facing screens are C4's (Dias's) to
 * design and will be added incrementally over the coming months. */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
