import React, { useState } from 'react';
import { X, Copy, Check, Download, FileDiff, ArrowRight, Terminal } from 'lucide-react';
import { computeLineDiff } from '../utils/diffUtils';

interface DiffModalProps {
  isOpen: boolean;
  onClose: () => void;
  originalCode: string;
  currentCode: string;
}

export const DiffModal: React.FC<DiffModalProps> = ({
  isOpen,
  onClose,
  originalCode,
  currentCode,
}) => {
  const [copied, setCopied] = useState(false);
  const diffResult = React.useMemo(() => {
    return computeLineDiff(originalCode, currentCode);
  }, [originalCode, currentCode]);

  if (!isOpen) return null;

  const handleCopyPatch = async () => {
    try {
      await navigator.clipboard.writeText(diffResult.unifiedDiff);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = diffResult.unifiedDiff;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <FileDiff className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-100 text-sm">Unified Git Diff & Patch Viewer</h3>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono border border-slate-700">
                  app.py
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-2">
                <span className="text-emerald-400 font-mono">+{diffResult.additions} lines</span>
                <span>•</span>
                <span className="text-rose-400 font-mono">-{diffResult.deletions} lines</span>
                <span>•</span>
                <span>{diffResult.hunks.length} diff hunk{diffResult.hunks.length !== 1 ? 's' : ''}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              id="copy-patch-btn"
              onClick={handleCopyPatch}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition"
              title="Copy unified diff to clipboard"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
              <span>{copied ? 'Copied Patch!' : 'Copy Patch'}</span>
            </button>
            <button
              id="download-patch-btn"
              onClick={handleDownloadPatch}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs flex items-center gap-1.5 transition"
              title="Download .patch file for git apply"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .patch</span>
            </button>
            <button
              id="close-diff-modal-btn"
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition ml-2"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Git Apply Quick Command Banner */}
        <div className="bg-slate-950/80 border-b border-slate-800/80 px-5 py-2 flex items-center justify-between text-xs font-mono text-slate-400">
          <div className="flex items-center gap-2">
            <Terminal className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span>Apply to your local clone:</span>
            <code className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700/80 text-emerald-300 select-all">
              git apply app_changes.patch
            </code>
          </div>
          <span className="text-[11px] text-slate-500 hidden sm:inline">Or pipe directly via clipboard: `pbpaste | git apply`</span>
        </div>

        {/* Diff Content Preview */}
        <div className="flex-1 overflow-auto p-4 bg-slate-950 font-mono text-xs leading-relaxed select-text">
          {diffResult.hunks.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <FileDiff className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-400" />
              <p>No changes detected between the original base code and current app.py.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {diffResult.hunks.map((hunk, hIdx) => (
                <div key={hIdx} className="border border-slate-800 rounded-lg overflow-hidden bg-slate-900/40">
                  {/* Hunk Header */}
                  <div className="bg-slate-900 px-3 py-1 text-slate-400 border-b border-slate-800 flex items-center justify-between text-[11px]">
                    <span className="text-indigo-300 font-semibold">
                      @@ -{hunk.oldStart},{hunk.oldLines} +{hunk.newStart},{hunk.newLines} @@
                    </span>
                    <span className="text-slate-500 text-[10px]">Hunk #{hIdx + 1}</span>
                  </div>

                  {/* Hunk Lines */}
                  <div className="divide-y divide-slate-800/40">
                    {hunk.lines.map((line, lIdx) => {
                      if (line.type === 'add') {
                        return (
                          <div key={lIdx} className="bg-emerald-950/30 text-emerald-200 px-3 py-0.5 flex items-start gap-2 hover:bg-emerald-950/50">
                            <span className="text-emerald-500/70 select-none w-4 shrink-0 font-bold">+</span>
                            <span className="select-none text-emerald-600/60 w-8 text-right text-[10px] shrink-0 font-mono">
                              {line.newLineNum}
                            </span>
                            <pre className="flex-1 overflow-x-auto whitespace-pre-wrap font-mono break-all">{line.text || ' '}</pre>
                          </div>
                        );
                      }
                      if (line.type === 'delete') {
                        return (
                          <div key={lIdx} className="bg-rose-950/30 text-rose-300 px-3 py-0.5 flex items-start gap-2 hover:bg-rose-950/50">
                            <span className="text-rose-500/70 select-none w-4 shrink-0 font-bold">-</span>
                            <span className="select-none text-rose-600/60 w-8 text-right text-[10px] shrink-0 font-mono">
                              {line.oldLineNum}
                            </span>
                            <pre className="flex-1 overflow-x-auto whitespace-pre-wrap font-mono break-all line-through opacity-80">{line.text || ' '}</pre>
                          </div>
                        );
                      }
                      return (
                        <div key={lIdx} className="text-slate-400 px-3 py-0.5 flex items-start gap-2 hover:bg-slate-800/30">
                          <span className="text-slate-600 select-none w-4 shrink-0"> </span>
                          <span className="select-none text-slate-600 w-8 text-right text-[10px] shrink-0 font-mono">
                            {line.newLineNum || line.oldLineNum}
                          </span>
                          <pre className="flex-1 overflow-x-auto whitespace-pre-wrap font-mono break-all">{line.text || ' '}</pre>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between text-xs text-slate-400">
          <span>Standard unified diff format compatible with `git apply`, `patch`, and GitHub PRs.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 transition font-medium"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
