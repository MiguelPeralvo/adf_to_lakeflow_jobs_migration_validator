import React from "react";

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div
      style={{
        padding: "12px 16px",
        background: "var(--red-dim)",
        border: "1px solid var(--red)",
        borderRadius: "var(--radius)",
        display: "flex",
        alignItems: "center",
        gap: 12,
        animation: "fadeInUp 0.3s ease",
      }}
    >
      <span style={{ color: "var(--red)", fontWeight: 600, fontSize: 16, flexShrink: 0 }}>\u26A0</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--red)", flex: 1 }}>
        {message}
      </span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            background: "none",
            border: "none",
            color: "var(--red)",
            cursor: "pointer",
            fontSize: 16,
            padding: 4,
          }}
        >
          \u2715
        </button>
      )}
    </div>
  );
}
