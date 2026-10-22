/** A live node-link diagram of the real C2 knowledge graph: every real Service and every
 * real REQUIRES edge, coloured by each service's real SO3 community. Nothing here is mock
 * data or a static picture -- every render is computed from /c2-api/api/graph/visual, which
 * queries the live Neo4j graph. A gold ring marks a service whose community was regenerated
 * in the last 10 minutes, so after running the SO3 ablation above, this panel can SHOW which
 * real part of the graph just changed, not just report a count.
 */
import { useEffect, useRef, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type Simulation,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { Loader2, RefreshCw, Waypoints } from "lucide-react";

interface GraphNodeIn {
  id: string;
  community: string | null;
  agency: string | null;
  recently_updated: boolean;
}
interface GraphEdgeIn {
  source: string;
  target: string;
}

interface SimNode extends GraphNodeIn, SimulationNodeDatum {}
type SimLink = SimulationLinkDatum<SimNode>;

const WIDTH = 760;
const HEIGHT = 480;

function communityColor(id: string | null): string {
  if (!id) return "#9ca3af";
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return `hsl(${hash % 360}, 62%, 52%)`;
}

function asNode(x: SimLink["source"] | SimLink["target"]): SimNode | null {
  return typeof x === "object" ? (x as SimNode) : null;
}

export default function ServiceGraph() {
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<SimLink[]>([]);
  const [hover, setHover] = useState<SimNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, bump] = useState(0);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/c2-api/api/graph/visual");
      if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
      const data: { nodes: GraphNodeIn[]; edges: GraphEdgeIn[] } = await res.json();

      simRef.current?.stop();
      const simNodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
      const simLinks: SimLink[] = data.edges.map((e) => ({ source: e.source, target: e.target }));

      const sim = forceSimulation(simNodes)
        .force(
          "link",
          forceLink<SimNode, SimLink>(simLinks)
            .id((d) => d.id)
            .distance(34)
            .strength(0.35),
        )
        .force("charge", forceManyBody().strength(-45))
        .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
        .force("collide", forceCollide(7))
        .on("tick", () => bump((x) => x + 1))
        .on("end", () => bump((x) => x + 1));

      simRef.current = sim;
      setNodes(simNodes);
      setLinks(simLinks);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    return () => {
      simRef.current?.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const recentCount = nodes.filter((n) => n.recently_updated).length;

  return (
    <div className="rounded-2xl border border-line bg-paper overflow-hidden shadow-2xs">
      <div className="px-5 py-4 bg-paper-2 border-b border-line flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-ink flex items-center gap-2">
            <Waypoints size={15} className="text-amber-600" />
            Live Service Graph
          </h3>
          <p className="text-xs text-ink-2 mt-1 leading-relaxed max-w-xl">
            Every real Service and REQUIRES edge right now, coloured by its real SO3
            community. A gold ring marks a community regenerated in the last 10 minutes --
            run a benchmark above, then click Refresh here to see it light up.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-paper hover:bg-paper-3 px-3 py-1.5 text-xs font-bold text-ink-2 hover:text-ink transition-all disabled:opacity-40 cursor-pointer shadow-2xs shrink-0"
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          <span>Refresh graph</span>
        </button>
      </div>
      <div className="p-3">
        {error && (
          <div className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2 mb-2">
            Failed: {error}
          </div>
        )}
        {recentCount > 0 && (
          <div className="text-xs text-amber-700 dark:text-amber-400 font-semibold mb-2">
            {recentCount} service(s) with a gold ring were regenerated in the last 10 minutes.
          </div>
        )}
        <svg
          width="100%"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="bg-paper-2 rounded-xl border border-line"
        >
          {links.map((l, i) => {
            const s = asNode(l.source);
            const t = asNode(l.target);
            if (!s || !t || s.x == null || t.x == null) return null;
            return (
              <line
                key={i}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke="currentColor"
                className="text-ink-3"
                strokeWidth={1}
                opacity={0.4}
              />
            );
          })}
          {nodes.map((n) => {
            if (n.x == null || n.y == null) return null;
            return (
              <circle
                key={n.id}
                cx={n.x}
                cy={n.y}
                r={n.recently_updated ? 6.5 : 4.5}
                fill={communityColor(n.community)}
                stroke={n.recently_updated ? "#f59e0b" : "transparent"}
                strokeWidth={n.recently_updated ? 2.5 : 0}
                onMouseEnter={() => setHover(n)}
                onMouseLeave={() => setHover((h) => (h?.id === n.id ? null : h))}
                style={{ cursor: "pointer" }}
              />
            );
          })}
        </svg>
        <div className="mt-2 text-xs min-h-[18px]">
          {hover ? (
            <>
              <span className="font-mono font-bold text-ink">{hover.id}</span>
              {hover.agency && <span className="text-ink-2"> &middot; {hover.agency}</span>}
              {hover.community && (
                <span className="text-ink-3 font-mono"> &middot; {hover.community}</span>
              )}
              {hover.recently_updated && (
                <span className="text-amber-600 dark:text-amber-400 font-bold">
                  {" "}
                  &middot; recently regenerated
                </span>
              )}
            </>
          ) : (
            <span className="text-ink-3">
              {nodes.length} services, {links.length} dependency edges &middot; hover a dot for
              details
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
