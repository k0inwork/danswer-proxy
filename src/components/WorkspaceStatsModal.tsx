import React from 'react';
import {
  X,
  Layers,
  FileCode2,
  BookOpen,
  ShieldCheck,
  Settings,
  Archive,
  BarChart3,
  HardDrive,
  FolderTree
} from 'lucide-react';
import { WorkspaceFile } from '../data/workspaceFiles';

interface WorkspaceStatsModalProps {
  isOpen: boolean;
  onClose: () => void;
  files: WorkspaceFile[];
  fileContents: Record<string, string>;
  onSelectFile: (fileId: string) => void;
}

export const WorkspaceStatsModal: React.FC<WorkspaceStatsModalProps> = ({
  isOpen,
  onClose,
  files,
  fileContents,
  onSelectFile,
}) => {
  if (!isOpen) return null;

  const totalLines = files.reduce((acc, f) => {
    const content = fileContents[f.id] ?? f.initialContent;
    return acc + content.split('\n').length;
  }, 0);

  const totalBytes = files.reduce((acc, f) => {
    const content = fileContents[f.id] ?? f.initialContent;
    return acc + new Blob([content]).size;
  }, 0);

  const totalKB = (totalBytes / 1024).toFixed(1);

  // Group by category
  const categories = [
    { key: 'orchestrator', label: 'Orchestrator Core', color: 'bg-emerald-500', text: 'text-emerald-400' },
    { key: 'tests', label: 'Tests & Verification', color: 'bg-teal-500', text: 'text-teal-400' },
    { key: 'docs', label: 'Architecture & Specs', color: 'bg-indigo-500', text: 'text-indigo-400' },
    { key: 'config', label: 'Configurations', color: 'bg-amber-500', text: 'text-amber-400' },
    { key: 'entrypoint', label: 'Entrypoint', color: 'bg-blue-500', text: 'text-blue-400' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col overflow-hidden max-h-[85vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <BarChart3 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100 text-base">Workspace Repository Statistics</h3>
              <p className="text-xs text-slate-400">Deep structural breakdown across all modules and tests</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* Top Metric Cards */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-center">
              <div className="text-xs text-slate-400 font-mono">Total Files</div>
              <div className="text-xl font-bold text-slate-100 mt-1 font-mono">{files.length}</div>
            </div>
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-center">
              <div className="text-xs text-slate-400 font-mono">Lines of Code</div>
              <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">{totalLines.toLocaleString()}</div>
            </div>
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-center">
              <div className="text-xs text-slate-400 font-mono">Total Size</div>
              <div className="text-xl font-bold text-indigo-400 mt-1 font-mono">{totalKB} KB</div>
            </div>
          </div>

          {/* Category Breakdown */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Category Distribution
            </h4>

            <div className="space-y-2">
              {categories.map((cat) => {
                const catFiles = files.filter((f) => f.category === cat.key);
                if (catFiles.length === 0) return null;
                const catLines = catFiles.reduce((acc, f) => {
                  const content = fileContents[f.id] ?? f.initialContent;
                  return acc + content.split('\n').length;
                }, 0);
                const percent = Math.round((catLines / totalLines) * 100);

                return (
                  <div key={cat.key} className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className={`font-semibold ${cat.text}`}>{cat.label}</span>
                      <span className="text-slate-400">
                        {catFiles.length} files • {catLines} lines ({percent}%)
                      </span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`${cat.color} h-full rounded-full transition-all duration-300`}
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* File Inventory List with clickable links */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              All Indexed Files
            </h4>
            <div className="border border-slate-800 rounded-xl bg-slate-950/60 divide-y divide-slate-800/60 max-h-48 overflow-y-auto">
              {files.map((file) => {
                const content = fileContents[file.id] ?? file.initialContent;
                const linesCount = content.split('\n').length;
                const sizeKB = (new Blob([content]).size / 1024).toFixed(1);

                return (
                  <button
                    key={file.id}
                    onClick={() => {
                      onSelectFile(file.id);
                      onClose();
                    }}
                    className="w-full text-left px-3.5 py-2 flex items-center justify-between text-xs hover:bg-slate-800/40 transition group font-mono"
                  >
                    <span className="text-slate-300 group-hover:text-emerald-300 truncate">
                      {file.path}
                    </span>
                    <div className="flex items-center gap-3 text-slate-500 text-[11px] shrink-0">
                      <span>{linesCount} lines</span>
                      <span>{sizeKB} KB</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950 flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
