import React from "react";

export function TopHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="fixed top-0 right-0 left-[220px] h-16 bg-[#060a13]/80 backdrop-blur-xl flex justify-between items-center px-10 z-40 shadow-2xl shadow-blue-900/10">
      <div className="flex items-center gap-4">
        <span className="text-xl font-black text-slate-50 font-headline uppercase tracking-tighter">
          LMV Engine
        </span>
        <div className="h-4 w-[1px] bg-white/10" />
        <span className="text-slate-400 text-sm">{title}</span>
      </div>
      <div className="flex items-center gap-4 text-slate-400">
        <button className="hover:text-white transition-opacity opacity-80 hover:opacity-100">
          <span className="material-symbols-outlined">notifications</span>
        </button>
        <button className="hover:text-white transition-opacity opacity-80 hover:opacity-100">
          <span className="material-symbols-outlined">settings</span>
        </button>
      </div>
    </header>
  );
}
