import React, { useState, useEffect, useCallback } from "react";
import { Sidebar, type Page } from "./components/Sidebar";
import { ValidatePage } from "./pages/Validate";
import { ExpressionPage } from "./pages/Expression";
import { HarnessPage } from "./pages/Harness";
import { ParallelPage } from "./pages/Parallel";
import { BatchPage } from "./pages/Batch";
import { SyntheticPage } from "./pages/Synthetic";
import { HistoryPage } from "./pages/History";

const PAGES: Record<Page, React.FC<{ entityId?: string | null }>> = {
  validate: ValidatePage,
  expression: ExpressionPage,
  harness: HarnessPage,
  parallel: ParallelPage,
  batch: BatchPage,
  synthetic: SyntheticPage,
  history: HistoryPage,
};

const VALID_PAGES = new Set(Object.keys(PAGES));

interface RouteState {
  page: Page;
  entityId: string | null;
}

function routeFromHash(): RouteState {
  const raw = window.location.hash.replace("#/", "").replace("#", "");
  const [pathPart] = raw.split("?");
  const segments = pathPart.split("/");
  const page = VALID_PAGES.has(segments[0]) ? (segments[0] as Page) : "validate";
  const entityId = segments[1] || null;
  return { page, entityId };
}

interface Capabilities {
  judge?: boolean;
  harness?: boolean;
  parallel?: boolean;
}

export function App() {
  const [route, setRoute] = useState<RouteState>(routeFromHash);
  const [capabilities, setCapabilities] = useState<Capabilities>({});

  const navigate = useCallback((p: Page, entityId?: string | null) => {
    const hash = entityId ? `#/${p}/${entityId}` : `#/${p}`;
    window.location.hash = hash;
    setRoute({ page: p, entityId: entityId ?? null });
  }, []);

  useEffect(() => {
    function onHashChange() {
      setRoute(routeFromHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // Fetch capabilities from backend
  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((data) =>
        setCapabilities({
          judge: data.judge,
          harness: data.harness,
          parallel: data.parallel,
        })
      )
      .catch(() => {});
  }, []);

  const ActivePage = PAGES[route.page];

  return (
    <div className="flex min-h-screen bg-base">
      <Sidebar active={route.page} onNavigate={(p) => navigate(p)} capabilities={capabilities} />
      <main className="flex-1 ml-[220px] h-screen overflow-y-auto">
        <ActivePage key={route.entityId || "fresh"} entityId={route.entityId} />
      </main>
    </div>
  );
}
