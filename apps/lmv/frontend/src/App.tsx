import React, { useState } from "react";
import { Sidebar, type Page } from "./components/Sidebar";
import { ValidatePage } from "./pages/Validate";
import { HarnessPage } from "./pages/Harness";
import { ParallelPage } from "./pages/Parallel";
import { HistoryPage } from "./pages/History";

const PAGES: Record<Page, () => React.JSX.Element> = {
  validate: ValidatePage,
  harness: HarnessPage,
  parallel: ParallelPage,
  history: HistoryPage,
};

export function App() {
  const [page, setPage] = useState<Page>("validate");
  const ActivePage = PAGES[page];

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar active={page} onNavigate={setPage} />
      <main
        style={{
          flex: 1,
          padding: "32px 40px",
          maxWidth: 1100,
          overflowY: "auto",
        }}
      >
        <ActivePage />
      </main>
    </div>
  );
}
