import React, { useState } from 'react';
import {
  X,
  Archive,
  FileDiff,
  FileCode2,
  BookOpen,
  Copy,
  Check,
  Download,
  Terminal,
  FolderArchive,
  Layers,
  Sparkles
} from 'lucide-react';
import { RepoFile, downloadRepoAsZip } from '../utils/zipUtils';
import { computeLineDiff } from '../utils/diffUtils';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  files: RepoFile[];
  originalAppPython: string;
  currentAppPython: string;
  onOpenDiffViewer: () => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  files,
  originalAppPython,
  currentAppPython,
  onOpenDiffViewer,
}) => {
  const [copiedPatch, setCopiedPatch] = useState(false);
  const [isExportingZip, setIsExportingZip] = useState(false);

  const diffResult = React.useMemo(() => {
    return computeLineDiff(originalAppPython, currentAppPython);
  }, [originalAppPython, currentAppPython]);

  if (!isOpen) return null;

  const handleDownloadZip = async () => {
    try {
      setIsExportingZip(true);
      await downloadRepoAsZip(files, 'danswer-onyx-orchestrator.zip');
    } catch (err) {
      console.error('Failed to generate ZIP archive:', err);
    } finally {
      setIsExportingZip(false);
    }
  };

  const handleDownloadPatch = () => {
    const blob = new Blob([diffResult.unifiedDiff], { type: 'text/x-diff;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'app_changes.patch';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyPatch = async () => {
    try {
      await navigator.clipboard.writeText(diffResult.unifiedDiff);
      setCopiedPatch(true);
      setTimeout(() => setCopiedPatch(false), 2000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = diffResult.unifiedDiff;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopiedPatch(true);
      setTimeout(() => setCopiedPatch(false), 2000);
    }
  };

  const totalBytes = files.reduce((acc, f) => acc + new Blob([f.content]).size, 0);
  const totalKB = (totalBytes / 1024).toFixed(1);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl w-full max-w-3xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <FolderArchive className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100 text-base">Export Repository & Changes</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Download the complete codebase as a ZIP or export a git patch for quick integration.
              </p>
            </div>
          </div>

          <button
            id="close-export-modal-btn"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6 overflow-y-auto max-h-[75vh]">
          {/* Main Primary Action Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* ZIP Export Card */}
            <div className="bg-slate-950/70 border border-slate-800 hover:border-emerald-500/50 rounded-xl p-5 flex flex-col justify-between transition group">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <Archive className="w-5 h-5" />
                  </div>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/60">
                    {files.length} files • {totalKB} KB
                  </span>
                </div>
                <h4 className="font-semibold text-slate-100 text-sm mb-1 group-hover:text-emerald-300 transition">
                  Complete Project ZIP
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Bundles all Python source, specifications, refactoring docs, test plans, and configurations into a ready-to-extract ZIP archive.
                </p>
              </div>

              <button
                id="export-zip-btn"
                onClick={handleDownloadZip}
                disabled={isExportingZip}
                className="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-xs transition disabled:opacity-50"
              >
                <Download className="w-4 h-4" />
                <span>{isExportingZip ? 'Packaging ZIP...' : 'Download Full Repo (.zip)'}</span>
              </button>
            </div>

            {/* Git Patch Export Card */}
            <div className="bg-slate-950/70 border border-slate-800 hover:border-indigo-500/50 rounded-xl p-5 flex flex-col justify-between transition group">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    <FileDiff className="w-5 h-5" />
                  </div>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/60">
                    <span className="text-emerald-400">+{diffResult.additions}</span> / <span className="text-rose-400">-{diffResult.deletions}</span>
                  </span>
                </div>
                <h4 className="font-semibold text-slate-100 text-sm mb-1 group-hover:text-indigo-300 transition">
                  Unified Git Patch (.patch)
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Export standard unified diff format compatible with <code className="text-indigo-300 font-mono">git apply</code> to apply all modifications to any existing clone.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  id="copy-git-patch-btn"
                  onClick={handleCopyPatch}
                  className="py-2.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs flex items-center justify-center gap-1.5 border border-slate-700 transition"
                >
                  {copiedPatch ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
                  <span>{copiedPatch ? 'Copied!' : 'Copy Patch'}</span>
                </button>
                <button
                  id="export-patch-btn"
                  onClick={handleDownloadPatch}
                  className="py-2.5 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center justify-center gap-1.5 shadow-xs transition"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download .patch</span>
                </button>
              </div>
            </div>
          </div>

          {/* Quick Git Apply Terminal Tip */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 flex items-center justify-between text-xs font-mono text-slate-400">
            <div className="flex items-center gap-2.5">
              <Terminal className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>To apply patch to your codebase:</span>
              <code className="bg-slate-900 px-2 py-0.5 rounded text-emerald-300 border border-slate-800">
                git apply app_changes.patch
              </code>
            </div>
            <button
              onClick={() => {
                onClose();
                onOpenDiffViewer();
              }}
              className="text-xs text-indigo-400 hover:text-indigo-300 underline font-sans flex items-center gap-1 shrink-0"
            >
              <FileDiff className="w-3.5 h-3.5" />
              <span>Inspect visual diff</span>
            </button>
          </div>

          {/* Included Files Inventory Table */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-slate-500" />
                Files Included in ZIP Package
              </h4>
              <span className="text-[11px] text-slate-500 font-mono">{files.length} items</span>
            </div>

            <div className="border border-slate-800 rounded-xl bg-slate-950/50 divide-y divide-slate-800/60 max-h-48 overflow-y-auto">
              {files.map((file, idx) => {
                const sizeKB = (new Blob([file.content]).size / 1024).toFixed(1);
                const isPy = file.path.endsWith('.py');
                const isDoc = file.path.endsWith('.md');
                return (
                  <div key={idx} className="px-3.5 py-2 flex items-center justify-between text-xs hover:bg-slate-800/30">
                    <div className="flex items-center gap-2.5">
                      {isPy ? (
                        <FileCode2 className="w-3.5 h-3.5 text-emerald-400" />
                      ) : isDoc ? (
                        <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                      ) : (
                        <Sparkles className="w-3.5 h-3.5 text-slate-500" />
                      )}
                      <span className="font-mono text-slate-300">{file.path}</span>
                    </div>
                    <span className="font-mono text-slate-500 text-[11px]">{sizeKB} KB</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/90 flex items-center justify-between text-xs text-slate-400">
          <span>Client-side generated archives using standard DEFLATE compression.</span>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
