import React from "react";

export type Page = "validate" | "harness" | "parallel" | "history";

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "validate", label: "Validate", icon: "\u2713" },
  { id: "harness", label: "Harness", icon: "\u21BB" },
  { id: "parallel", label: "Parallel", icon: "\u21C4" },
  { id: "history", label: "History", icon: "\u29D6" },
];

export function Sidebar({
  active,
  onNavigate,
}: {
  active: Page;
  onNavigate: (page: Page) => void;
}) {
  return (
    <nav
      style={{
        width: 220,
        height: "100vh",
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        padding: "24px 0",
        flexShrink: 0,
        position: "sticky",
        top: 0,
      }}
    >
      <div style={{ padding: "0 20px", marginBottom: 36 }}>
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 17,
            color: "var(--text-primary)",
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
          }}
        >
          Lakeflow
          <br />
          <span style={{ color: "var(--accent)" }}>Migration Validator</span>
        </div>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: "var(--text-muted)",
            marginTop: 6,
            letterSpacing: "0.04em",
          }}
        >
          LMV v0.1.0
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 2, padding: "0 10px" }}>
        {NAV.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 12px",
                border: "none",
                borderRadius: "var(--radius)",
                background: isActive ? "var(--accent-dim)" : "transparent",
                color: isActive ? "var(--accent)" : "var(--text-secondary)",
                cursor: "pointer",
                transition: "all var(--transition)",
                fontWeight: isActive ? 600 : 400,
                fontSize: 13,
                textAlign: "left",
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = "var(--bg-hover)";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = "transparent";
              }}
            >
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  background: isActive ? "var(--accent)" : "var(--bg-elevated)",
                  color: isActive ? "#fff" : "var(--text-muted)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 14,
                  fontWeight: 600,
                  flexShrink: 0,
                  transition: "all var(--transition)",
                }}
              >
                {item.icon}
              </span>
              {item.label}
            </button>
          );
        })}
      </div>

      <div style={{ flex: 1 }} />

      <div
        style={{
          padding: "14px 20px",
          borderTop: "1px solid var(--border)",
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: "var(--text-muted)",
          lineHeight: 1.6,
        }}
      >
        ADF \u2192 Databricks
        <br />
        Lakeflow Jobs
      </div>
    </nav>
  );
}
