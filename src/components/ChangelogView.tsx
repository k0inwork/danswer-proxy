import React, { useState } from 'react';
import { CHANGELOG } from '../data/app4Code';
import { ShieldAlert, Zap, Cpu, Sparkles, CheckCircle2, FileCode } from 'lucide-react';

export const ChangelogView: React.FC = () => {
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [expandedDiff, setExpandedDiff] = useState<Record<string, boolean>>({
    'tool-json-corruption': true,
    'history-bloat-504': true,
    'system-reminder-pollution': true,
    'network-resilience-retries': false,
    'detector-leak-prevention': false,
    'xml-hallucination-instructions': false,
  });

  const toggleExpand = (id: string) => {
    setExpandedDiff((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const categories = ['All', 'Fix', 'Performance', 'Resilience', 'Sanitization'];

  const filteredItems = activeCategory === 'All'
    ? CHANGELOG
    : CHANGELOG.filter((item) => item.category === activeCategory);

  const getCategoryIcon = (cat: string) => {
    switch (cat) {
      case 'Fix':
        return <ShieldAlert className="w-4 h-4 text-rose-400" />;
      case 'Performance':
        return <Zap className="w-4 h-4 text-amber-400" />;
      case 'Resilience':
        return <Cpu className="w-4 h-4 text-purple-400" />;
      default:
        return <Sparkles className="w-4 h-4 text-emerald-400" />;
    }
  };

  const getSeverityBadge = (sev: string) => {
    switch (sev) {
      case 'Critical':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/30';
      case 'High':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/30';
      default:
        return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
    }
  };

  return (
    <div className="space-y-6">
      {/* Category Pills */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-3 rounded-xl">
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition ${
                activeCategory === cat
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="text-xs text-slate-400">
          Showing <span className="text-slate-200 font-semibold">{filteredItems.length}</span> enhancements
        </div>
      </div>

      {/* Changelog Cards */}
      <div className="space-y-4">
        {filteredItems.map((item, index) => {
          const isExpanded = expandedDiff[item.id];
          return (
            <div
              key={item.id}
              className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-md transition hover:border-slate-700"
            >
              {/* Card Header */}
              <div className="p-4 sm:p-5 border-b border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900/60">
                <div className="flex items-start sm:items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0">
                    {getCategoryIcon(item.category)}
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-emerald-400 font-semibold">
                        #{index + 1}
                      </span>
                      <h3 className="text-sm sm:text-base font-semibold text-white">
                        {item.title}
                      </h3>
                      <span
                        className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${getSeverityBadge(
                          item.severity
                        )}`}
                      >
                        {item.severity}
                      </span>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => toggleExpand(item.id)}
                  className="self-end sm:self-auto px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
                >
                  {isExpanded ? 'Hide Code Diff' : 'View Code Diff'}
                </button>
              </div>

              {/* Card Body */}
              <div className="p-4 sm:p-5 space-y-4 text-xs sm:text-sm">
                {/* Symptom in Logs */}
                <div className="bg-rose-950/20 border border-rose-900/30 rounded-lg p-3">
                  <span className="font-semibold text-rose-300 block mb-1 text-xs uppercase tracking-wide">
                    ⚠️ Symptom Detected in Logs:
                  </span>
                  <p className="text-slate-300 font-mono text-xs leading-relaxed">
                    {item.symptomInLogs}
                  </p>
                </div>

                {/* Root Cause & Solution */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3.5">
                    <span className="font-semibold text-amber-400 block mb-1 text-xs uppercase tracking-wide">
                      🔍 Root Cause Analysis:
                    </span>
                    <p className="text-slate-300 text-xs leading-relaxed">
                      {item.rootCause}
                    </p>
                  </div>

                  <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3.5">
                    <span className="font-semibold text-emerald-400 block mb-1 text-xs uppercase tracking-wide flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      App v4 Resolution:
                    </span>
                    <p className="text-slate-300 text-xs leading-relaxed">
                      {item.solution}
                    </p>
                  </div>
                </div>

                {/* Before / After Code Diff */}
                {isExpanded && (
                  <div className="mt-4 pt-3 border-t border-slate-800 space-y-2">
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
                      <FileCode className="w-3.5 h-3.5 text-slate-400" />
                      {item.diffHighlight.file}
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 font-mono text-xs">
                      {/* Before */}
                      <div className="bg-rose-950/20 border border-rose-900/40 rounded-lg overflow-hidden">
                        <div className="bg-rose-950/40 px-3 py-1.5 text-rose-300 font-semibold border-b border-rose-900/40 text-[11px]">
                          ❌ App v3 (Problematic)
                        </div>
                        <pre className="p-3 text-rose-200/90 whitespace-pre-wrap overflow-x-auto leading-relaxed">
                          {item.diffHighlight.before}
                        </pre>
                      </div>

                      {/* After */}
                      <div className="bg-emerald-950/20 border border-emerald-900/40 rounded-lg overflow-hidden">
                        <div className="bg-emerald-950/40 px-3 py-1.5 text-emerald-300 font-semibold border-b border-emerald-900/40 text-[11px]">
                          ✅ App v4 (Enhanced)
                        </div>
                        <pre className="p-3 text-emerald-200 whitespace-pre-wrap overflow-x-auto leading-relaxed">
                          {item.diffHighlight.after}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
