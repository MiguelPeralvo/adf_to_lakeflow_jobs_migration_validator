import React from "react";

export type Page = "validate" | "harness" | "parallel" | "history";

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "validate", label: "Validate", icon: "rule" },
  { id: "harness", label: "Harness", icon: "settings_input_component" },
  { id: "parallel", label: "Parallel", icon: "account_tree" },
  { id: "history", label: "History", icon: "history" },
];

export function Sidebar({
  active,
  onNavigate,
}: {
  active: Page;
  onNavigate: (page: Page) => void;
}) {
  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] bg-surface flex flex-col border-r border-white/5 z-50">
      <div className="p-6">
        <h1 className="text-lg font-bold tracking-tight text-slate-100 font-headline">
          Lakeflow Migration Validator
        </h1>
        <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-1">
          LMV v0.1.0
        </p>
      </div>

      <nav className="flex-1 mt-4 px-2 space-y-1">
        {NAV.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`flex items-center gap-3 px-4 py-3 w-full text-left transition-all duration-200 ${
                isActive
                  ? "text-accent font-semibold bg-surface-container border-r-4 border-accent"
                  : "text-slate-400 hover:text-slate-100 hover:bg-surface-container"
              }`}
            >
              <span className="material-symbols-outlined text-sm">{item.icon}</span>
              <span className="font-body text-sm">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="p-4 mt-auto">
        <div className="rounded-xl p-4 bg-surface-container-low border border-outline-variant/10">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary-container/20 flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-sm">database</span>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 font-mono">ADF → Databricks</p>
              <p className="text-xs font-bold text-slate-300">Lakeflow Jobs</p>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
