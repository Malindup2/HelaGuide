import { Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import Admin from "./pages/Admin";

/** Root routes. Only Home exists on the citizen side so far -- the
 * conversation flow, guided mode, and the rest of those screens are C4's
 * (Dias's) to design and will be added incrementally over the coming
 * months. /admin is C2's own review tool, not part of that citizen flow. */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/admin" element={<Admin />} />
    </Routes>
  );
}
