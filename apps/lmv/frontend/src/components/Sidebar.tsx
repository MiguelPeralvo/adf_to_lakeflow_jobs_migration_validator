import React from "react";

export type Page =
  | "validate"
  | "expression"
  | "harness"
  | "parallel"
  | "batch"
  | "synthetic"
  | "history";

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "validate", label: "Validate", icon: "rule" },
  { id: "expression", label: "Expression", icon: "gavel" },
  { id: "harness", label: "End to End Harness", icon: "settings_input_component" },
  { id: "parallel", label: "Parallel Testing", icon: "account_tree" },
  { id: "batch", label: "Batch Validation", icon: "monitoring" },
  { id: "synthetic", label: "Synthetic", icon: "science" },
  { id: "history", label: "History", icon: "history" },
];

export function Sidebar({
  active,
  onNavigate,
  capabilities,
}: {
  active: Page;
  onNavigate: (page: Page) => void;
  capabilities?: { judge?: boolean; harness?: boolean; parallel?: boolean };
}) {
  const caps = capabilities || {};

  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] bg-[#0f131d] flex flex-col border-r border-white/5 z-50">
      <div className="p-6">
        <h1 className="text-lg font-bold tracking-tight text-slate-100 font-headline">
          Lakeflow Migration Validator
        </h1>
        <p className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mt-1">
          LMV v0.1.0
        </p>
      </div>

      <nav className="flex-1 mt-2 px-3 space-y-0.5">
        {NAV.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`flex items-center gap-3 px-4 py-2.5 w-full text-left transition-all duration-200 rounded-sm ${
                isActive
                  ? "text-[#2d7ff9] font-semibold bg-[#1b2029] border-r-4 border-[#2d7ff9]"
                  : "text-slate-400 hover:text-slate-100 hover:bg-[#1b2029]"
              }`}
            >
              <span className="material-symbols-outlined text-[20px] shrink-0">{item.icon}</span>
              <span className="text-sm font-medium truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Capability status */}
      <div className="p-4 mt-auto space-y-3">
        <div className="p-3 rounded-xl bg-surface-container-low border border-white/5">
          <p className="text-[9px] font-mono text-slate-500 uppercase tracking-widest mb-2">Backends</p>
          <div className="space-y-1.5">
            {[
              { name: "Validator", active: true },
              { name: "LLM Judge", active: caps.judge },
              { name: "Harness", active: caps.harness },
              { name: "Parallel", active: caps.parallel },
            ].map((b) => (
              <div key={b.name} className="flex items-center gap-2">
                <div
                  className={`w-1.5 h-1.5 rounded-full ${
                    b.active ? "bg-[#27e199]" : "bg-slate-600"
                  }`}
                />
                <span
                  className={`text-[10px] font-mono ${
                    b.active ? "text-slate-300" : "text-slate-600"
                  }`}
                >
                  {b.name}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
