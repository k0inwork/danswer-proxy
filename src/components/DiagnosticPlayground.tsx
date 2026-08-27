import React, { useState } from 'react';
import { Play, RotateCcw, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';

export const DiagnosticPlayground: React.FC = () => {
  const [xmlInput, setXmlInput] = useState(
    `<local_tool>\n  <name>Write</name>\n  <arguments>{"file_path": "/home/janis/DANSWER/app4.py", "content": "#!/usr/bin/env python3\nimport os\nprint(\\"Hello from app4\\")"}</arguments>\n</local_tool>`
  );

  const [rawUserPrompt, setRawUserPrompt] = useState(
    `analyze ~/DANSWER/app.py\n<system-reminder>snip_id=2awz5v; system-generated; for snip tool use only; do not discuss in thinking or responses.</system-reminder>`
  );

  const [historyTurnCount, setHistoryTurnCount] = useState<number>(18);

  // App v3 logic simulation
  const simulateV3ArgumentParse = (input: string) => {
    const match = input.match(/<local_tool>\s*<name>([^<]+?)<\/name>\s*<arguments>(.*?)<\/arguments>\s*<\/local_tool>/s);
    if (!match) return { error: 'No <local_tool> tag found' };

    const rawArgs = match[2].trim();
    try {
      const parsed = JSON.parse(rawArgs);
      return { status: 'SUCCESS', result: parsed };
    } catch {
      return {
        status: 'FAILED (Fallback to _raw)',
        result: { _raw: rawArgs },
        consequence: 'Downstream agent throws InputValidationError: required parameter `file_path` missing!',
      };
    }
  };

  // App v4 logic simulation with repair
  const simulateV4ArgumentParse = (input: string) => {
    const match = input.match(/<local_tool>\s*<name>([^<]+?)<\/name>\s*<arguments>(.*?)<\/arguments>\s*<\/local_tool>/s);
    if (!match) return { error: 'No <local_tool> tag found' };

    const toolName = match[1].trim();
    const rawArgs = match[2].trim();

    // 1. Try JSON.parse
    try {
      const parsed = JSON.parse(rawArgs);
      return { status: 'SUCCESS (Direct JSON)', result: parsed };
    } catch {
      // 2. Try sanitize newlines
      try {
        const sanitized = rawArgs.replace(/[\r\n]+/g, '\\n');
        const parsed = JSON.parse(sanitized);
        return { status: 'SUCCESS (Sanitized Newlines)', result: parsed };
      } catch {
        // 3. Heuristic
        const extracted: Record<string, string> = {};
        const fp = rawArgs.match(/"file_path"\s*:\s*"([^"]+)"/);
        if (fp) extracted.file_path = fp[1];

        const content = rawArgs.match(/"content"\s*:\s*"(.*)"\s*\}?$/s);
        if (content) extracted.content = content[1];

        const cmd = rawArgs.match(/"command"\s*:\s*"([^"]+)"/);
        if (cmd) extracted.command = cmd[1];

        if (Object.keys(extracted).length > 0) {
          return {
            status: 'SUCCESS (Heuristic Recovery)',
            result: extracted,
            consequence: 'Parameters successfully mapped, downstream agent executes seamlessly.',
          };
        }

        return { status: 'FALLBACK (_raw)', result: { _raw: rawArgs } };
      }
    }
  };

  const v3ParseResult = simulateV3ArgumentParse(xmlInput);
  const v4ParseResult = simulateV4ArgumentParse(xmlInput);

  // Prompt cleaner simulation
  const cleanedPrompt = rawUserPrompt
    .replace(/<system-reminder>.*?<\/system-reminder>/gs, '')
    .replace(/\[Request interrupted by user\]/g, '')
    .trim();

  // Payload calculation
  const v3EstBytes = 3500 + historyTurnCount * 4500;
  const v4EstBytes = 3500 + 400; // Only last round appended

  return (
    <div className="space-y-6">
      {/* Test 1: Tool JSON Parser & Repair Sandbox */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Play className="w-4 h-4 text-emerald-400" />
              1. Tool Argument Parser & Repair Simulator
            </h2>
            <p className="text-xs text-slate-400">
              Test how raw tool XML blocks are parsed and repaired when multi-line code creates unescaped JSON.
            </p>
          </div>
          <button
            onClick={() =>
              setXmlInput(
                `<local_tool>\n  <name>Write</name>\n  <arguments>{"file_path": "/home/janis/DANSWER/app4.py", "content": "#!/usr/bin/env python3\nimport os\nprint(\\"Hello from app4\\")"}</arguments>\n</local_tool>`
              )
            }
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 flex items-center gap-1.5 self-start sm:self-auto"
          >
            <RotateCcw className="w-3 h-3" />
            Reset Sample
          </button>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-1.5">
            Incoming Model Output Chunk (XML):
          </label>
          <textarea
            rows={4}
            value={xmlInput}
            onChange={(e) => setXmlInput(e.target.value)}
            className="w-full bg-slate-950 font-mono text-xs text-slate-200 border border-slate-800 rounded-lg p-3 focus:outline-none focus:border-emerald-500"
          />
        </div>

        {/* Side-by-Side Parser Comparison */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* App v3 Result */}
          <div className="bg-slate-950 border border-rose-950/60 rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between border-b border-rose-900/30 pb-2">
              <span className="font-semibold text-rose-400 text-xs flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                App v3 Parser Outcome
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                {v3ParseResult.status || 'ERROR'}
              </span>
            </div>
            <pre className="font-mono text-xs text-slate-300 bg-slate-900/80 p-2.5 rounded border border-slate-800/80 overflow-x-auto max-h-48">
              {JSON.stringify(v3ParseResult.result, null, 2)}
            </pre>
            {v3ParseResult.consequence && (
              <p className="text-[11px] text-rose-300 font-mono mt-1">
                ⚠️ {v3ParseResult.consequence}
              </p>
            )}
          </div>

          {/* App v4 Result */}
          <div className="bg-slate-950 border border-emerald-950/60 rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between border-b border-emerald-900/30 pb-2">
              <span className="font-semibold text-emerald-400 text-xs flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                App v4 Enhanced Parser Outcome
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                {v4ParseResult.status || 'SUCCESS'}
              </span>
            </div>
            <pre className="font-mono text-xs text-slate-200 bg-slate-900/80 p-2.5 rounded border border-slate-800/80 overflow-x-auto max-h-48">
              {JSON.stringify(v4ParseResult.result, null, 2)}
            </pre>
            {v4ParseResult.consequence && (
              <p className="text-[11px] text-emerald-300 font-mono mt-1">
                ✅ {v4ParseResult.consequence}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Test 2: Payload History Bloat & Latency Calculator */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="border-b border-slate-800 pb-3">
          <h2 className="text-base font-semibold text-white">
            2. Context History Bloat & Gateway 504 Protection
          </h2>
          <p className="text-xs text-slate-400">
            Compare payload sizes sent to Onyx/Danswer across multi-turn sessions (App v3 full accumulation vs App v4 trailing context).
          </p>
        </div>

        <div>
          <div className="flex justify-between items-center text-xs text-slate-300 mb-2">
            <span>Simulated Conversation Turn Count: <strong className="text-emerald-400">{historyTurnCount} turns</strong></span>
            <span className="text-slate-400">Avg. 4.5 KB per tool output</span>
          </div>
          <input
            type="range"
            min="2"
            max="40"
            value={historyTurnCount}
            onChange={(e) => setHistoryTurnCount(Number(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          <div className="bg-slate-950 border border-rose-900/30 rounded-xl p-4">
            <span className="text-xs font-semibold text-rose-400 uppercase tracking-wide block mb-1">
              App v3 (Cumulative History Extractor)
            </span>
            <div className="text-2xl font-bold font-mono text-rose-200 mb-1">
              ~{(v3EstBytes / 1024).toFixed(1)} KB
            </div>
            <p className="text-xs text-slate-400">
              {v3EstBytes > 100000 ? (
                <span className="text-rose-400 font-semibold">
                  ⚠️ Critical: Exceeds 100 KB! Triggers 60s Nginx 504 Gateway Timeout.
                </span>
              ) : (
                'Concatenates all previous tool calls into every message payload.'
              )}
            </p>
          </div>

          <div className="bg-slate-950 border border-emerald-900/30 rounded-xl p-4">
            <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wide block mb-1">
              App v4 (Trailing Round Extractor)
            </span>
            <div className="text-2xl font-bold font-mono text-emerald-300 mb-1">
              ~{(v4EstBytes / 1024).toFixed(1)} KB
            </div>
            <p className="text-xs text-emerald-400/90 font-medium">
              ✅ Constant payload size ({Math.round(v3EstBytes / v4EstBytes)}x reduction). Instant responses without timeouts.
            </p>
          </div>
        </div>
      </div>

      {/* Test 3: System Reminder Sanitizer */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="border-b border-slate-800 pb-3">
          <h2 className="text-base font-semibold text-white">
            3. CLI System Reminder Sanitizer (clean_user_message)
          </h2>
          <p className="text-xs text-slate-400">
            Verify how internal agent framework tags are stripped before routing to persona detectors.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Raw Message from Agent Framework:
            </label>
            <textarea
              rows={3}
              value={rawUserPrompt}
              onChange={(e) => setRawUserPrompt(e.target.value)}
              className="w-full bg-slate-950 font-mono text-xs text-slate-200 border border-slate-800 rounded-lg p-2.5 focus:outline-none focus:border-emerald-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-emerald-400 mb-1.5 flex items-center gap-1">
              <ArrowRight className="w-3.5 h-3.5" />
              Sanitized Prompt passed to Onyx:
            </label>
            <div className="w-full min-h-[75px] bg-slate-950 font-mono text-xs text-emerald-300 border border-emerald-900/50 rounded-lg p-2.5 flex items-center">
              {cleanedPrompt || <span className="text-slate-600 italic">Empty prompt</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
