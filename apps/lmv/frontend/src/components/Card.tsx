import React from "react";

export function Card({
  children,
  style,
  className = "",
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}) {
  return (
    <div
      className={`bg-surface-container rounded-xl p-6 border border-outline-variant/10 shadow-xl ${className}`}
      style={style}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-2xl font-bold font-headline text-on-surface tracking-tight mb-5">
      {children}
    </h2>
  );
}
