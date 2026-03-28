import React, { useState, useEffect, useCallback } from "react";
import { Sidebar, type Page } from "./components/Sidebar";
import { ValidatePage } from "./pages/Validate";
import { ExpressionPage } from "./pages/Expression";
import { HarnessPage } from "./pages/Harness";
import { ParallelPage } from "./pages/Parallel";
import { BatchPage } from "./pages/Batch";
import { SyntheticPage } from "./pages/Synthetic";
import { HistoryPage } from "./pages/History";

const PAGES: Record<Page, () => React.JSX.Element> = {
  validate: ValidatePage,
  expression: ExpressionPage,
  harness: HarnessPage,
  parallel: ParallelPage,
  batch: BatchPage,
  synthetic: SyntheticPage,
  history: HistoryPage,
};

const VALID_PAGES = new Set(Object.keys(PAGES));

function pageFromHash(): Page {
  const hash = window.location.hash.replace("#/", "").replace("#", "");
  return VALID_PAGES.has(hash) ? (hash as Page) : "validate";
}

export function App() {
  const [page, setPage] = useState<Page>(pageFromHash);

  const navigate = useCallback((p: Page) => {
    window.location.hash = `#/${p}`;
    setPage(p);
  }, []);

  useEffect(() => {
    function onHashChange() {
      setPage(pageFromHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const ActivePage = PAGES[page];

  return (
    <div className="flex min-h-screen bg-base">
      <Sidebar active={page} onNavigate={navigate} />
      <main className="flex-1 ml-[220px] h-screen overflow-y-auto">
        <ActivePage />
      </main>
    </div>
  );
}
