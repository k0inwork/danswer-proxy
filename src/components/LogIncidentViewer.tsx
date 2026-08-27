import React from 'react';
import { LOG_SAMPLES } from '../data/app4Code';
import { Terminal, AlertCircle, Clock, CheckCircle2 } from 'lucide-react';

export const LogIncidentViewer: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Intro card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-2">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <Terminal className="w-4 h-4 text-emerald-400" />
          Log Incident Analysis & Timeline Mapping
        </h2>
        <p className="text-xs text-slate-400 leading-relaxed">
          The provided session logs revealed 4 distinct technical failures during the agent interaction session. Below is the mapped timeline of the incidents, their underlying causes in `app3.py`, and how `app4.py` prevents each failure.
        </p>
      </div>

      {/* Incident Cards */}
      <div className="space-y-4">
        {LOG_SAMPLES.map((log) => (
          <div
            key={log.turn + log.time}
            className="bg-slate-900 border border-slate-800 rounded-xl p-4 sm:p-5 shadow-sm space-y-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded text-xs font-mono font-bold bg-slate-800 text-slate-200 border border-slate-700">
                  Turn #{log.turn}
                </span>
                <span className="flex items-center gap-1 text-xs text-slate-400 font-mono">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  {log.time}
                </span>
              </div>

              <span
                className={`text-[11px] font-semibold uppercase px-2.5 py-0.5 rounded border ${
                  log.type === 'ERROR'
                    ? 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                    : log.type === 'TIMEOUT'
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                    : 'bg-blue-500/20 text-blue-300 border-blue-500/30'
                }`}
              >
                {log.type}
              </span>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-white mb-1 flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-rose-400" />
                {log.issue}
              </h3>
              <p className="text-xs text-slate-300 font-mono bg-slate-950 p-2.5 rounded border border-slate-800">
                {log.details}
              </p>
            </div>

            <div className="bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-3 text-xs text-emerald-300 flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-semibold text-emerald-200 mb-0.5">
                  App v4 Prevention:
                </strong>
                {log.type === 'ERROR' && (
                  <span>
                    `safe_parse_tool_arguments()` repairs JSON formatting and extracts `file_path` and `content` heuristically so no tool calls fail validation.
                  </span>
                )}
                {log.type === 'TIMEOUT' && (
                  <span>
                    `extract_last_tool_execution_context()` truncates payload down from 135KB to &lt;4KB, preventing Nginx 504 proxy timeout.
                  </span>
                )}
                {log.type === 'NETWORK' && (
                  <span>
                    `urllib3.util.retry.Retry` with backoff factor retries transient 502/504 errors up to 3 times before failing gracefully.
                  </span>
                )}
                {log.type === 'HALLUCINATION' && (
                  <span>
                    Explicit negative prompt rules added to `format_external_tools_for_danswer()` forbid the LLM from outputting speculative tool execution mockups.
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
