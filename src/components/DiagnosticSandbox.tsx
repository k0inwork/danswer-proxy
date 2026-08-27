import React, { useState } from 'react';
import {
  Play,
  RotateCcw,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Terminal,
  Cpu,
  ArrowRight,
  ShieldAlert,
  Layers,
  Code2
} from 'lucide-react';

export const DiagnosticSandbox: React.FC = () => {
  const [xmlInput, setXmlInput] = useState(
    `<local_tool>\n  <name>read_file</name>\n  <arguments>{\n    "file_path": "src/security/crypto.py"\n  }</arguments>\n</local_tool>`
  );

  const [promptInput, setPromptInput] = useState(
    `Please inspect src/security/crypto.py and audit token generation.\n<system-reminder>snip_id=994b; system-generated snip context; do not repeat.</system-reminder>`
  );

  const [simulateResult, setSimulateResult] = useState<any>(null);

  const runSimulation = () => {
    // 1. Tool XML match
    const toolMatch = xmlInput.match(/<local_tool>\s*<name>([^<]+?)<\/name>\s*<arguments>(.*?)<\/arguments>\s*<\/local_tool>/s);
    let toolParsed = null;
    let isGroundingIntercept = false;

    if (toolMatch) {
      const name = toolMatch[1].trim();
      const rawArgs = toolMatch[2].trim();
      let parsedArgs = null;
      let repairMethod = 'Standard JSON';

      try {
        parsedArgs = JSON.parse(rawArgs);
      } catch {
        try {
          const sanitized = rawArgs.replace(/[\r\n]+/g, '\\n');
          parsedArgs = JSON.parse(sanitized);
          repairMethod = 'Sanitized Newlines';
        } catch {
          const fp = rawArgs.match(/"file_path"\s*:\s*"([^"]+)"/);
          parsedArgs = { file_path: fp ? fp[1] : 'unknown', _repaired: true };
          repairMethod = 'Regex Heuristic Repair';
        }
      }

      isGroundingIntercept = ['read_file', 'Read', 'read_file_content'].includes(name);

      toolParsed = {
        name,
        arguments: parsedArgs,
        repairMethod,
        isGroundingIntercept,
      };
    }

    // 2. Prompt cleaning
    const cleanedPrompt = promptInput
      .replace(/<system-reminder>[\s\S]*?<\/system-reminder>/gi, '')
      .replace(/<system_reminder>[\s\S]*?<\/system_reminder>/gi, '')
      .trim();

    setSimulateResult({
      toolParsed,
      cleanedPrompt,
      timestamp: new Date().toLocaleTimeString(),
    });
  };

  return (
    <div className="p-6 sm:p-8 max-w-5xl mx-auto space-y-6 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100">Interactive Tool Parser & Intercept Sandbox</h2>
            <p className="text-xs text-slate-400 mt-1">
              Test streaming XML parsing, JSON argument repair heuristics, and prompt sanitization live.
            </p>
          </div>
        </div>

        <button
          onClick={runSimulation}
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-2 shadow-xs transition"
        >
          <Play className="w-3.5 h-3.5" />
          <span>Execute Parser Simulation</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left: Inputs */}
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
              <Code2 className="w-3.5 h-3.5 text-emerald-400" />
              Raw XML Tool Stream Chunk
            </label>
            <textarea
              value={xmlInput}
              onChange={(e) => setXmlInput(e.target.value)}
              rows={6}
              className="w-full bg-slate-950 border border-slate-800 focus:border-emerald-500 rounded-lg p-3 text-xs font-mono text-emerald-300 focus:outline-none"
            />
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5 text-indigo-400" />
              Raw User Prompt with Reminder Tags
            </label>
            <textarea
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              rows={4}
              className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none"
            />
          </div>
        </div>

        {/* Right: Simulated Pipeline Output */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 flex flex-col justify-between">
          <div className="space-y-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              Simulated Execution Output
            </h3>

            {simulateResult ? (
              <div className="space-y-3 font-mono text-xs">
                {/* Grounding Interception Badge */}
                {simulateResult.toolParsed?.isGroundingIntercept ? (
                  <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      AUTO-GROUNDING INTERCEPT ACTIVE
                    </div>
                    <p className="text-[11px] font-sans text-slate-300">
                      Tool call <code className="text-emerald-400 font-mono">{simulateResult.toolParsed.name}</code> intercepted. Blocking upload + project association triggered for <code className="text-emerald-400 font-mono">{simulateResult.toolParsed.arguments.file_path}</code> before redispatch.
                    </p>
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-400">
                    Standard local tool execution (no blocking upload required).
                  </div>
                )}

                {/* Parsed Arguments */}
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                  <div className="text-slate-500 text-[11px]">PARSED ARGUMENTS ({simulateResult.toolParsed?.repairMethod || 'N/A'}):</div>
                  <pre className="text-slate-200 overflow-x-auto text-[11px]">
                    {JSON.stringify(simulateResult.toolParsed?.arguments || {}, null, 2)}
                  </pre>
                </div>

                {/* Cleaned Prompt */}
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                  <div className="text-slate-500 text-[11px]">SANITIZED USER PROMPT:</div>
                  <div className="text-slate-300 font-sans text-xs">
                    {simulateResult.cleanedPrompt}
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-xs text-slate-500 font-mono">
                Click "Execute Parser Simulation" to run live inspection.
              </div>
            )}
          </div>

          <div className="text-[10px] font-mono text-slate-500 text-right pt-2 border-t border-slate-800">
            Powered by <code className="text-emerald-400">orchestrator.tool_parser</code>
          </div>
        </div>
      </div>
    </div>
  );
};
