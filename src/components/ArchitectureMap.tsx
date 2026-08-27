import React from 'react';
import {
  Layers,
  ArrowRight,
  Database,
  Cpu,
  RefreshCw,
  Server,
  FileCode2,
  Sliders,
  Sparkles,
  ShieldCheck,
  Zap,
  Terminal,
  Activity,
  Workflow
} from 'lucide-react';

interface ArchitectureMapProps {
  onSelectFile: (filePath: string) => void;
}

export const ArchitectureMap: React.FC<ArchitectureMapProps> = ({ onSelectFile }) => {
  const modules = [
    {
      id: 'orchestrator/config.py',
      name: 'config.py',
      title: 'Configuration & Safe Logging',
      icon: Sliders,
      badge: 'Core Config',
      color: 'border-blue-500/30 bg-blue-500/5 text-blue-400',
      description: 'Centralized environment variables, persona IDs, timeout configs, and sensitive Authorization header redaction.',
      functions: ['redact_headers()', 'log_incoming_request()', 'log_session_event()'],
    },
    {
      id: 'orchestrator/models.py',
      name: 'models.py',
      title: 'Domain Models & State Machines',
      icon: Database,
      badge: 'State Models',
      color: 'border-indigo-500/30 bg-indigo-500/5 text-indigo-400',
      description: 'Descriptor upload & attach state machine (PENDING_UPLOAD -> UPLOADING -> READY), Segment, and thread-safe SessionRegistry.',
      functions: ['DescriptorStatus', 'Descriptor.to_dict()', 'SessionRegistry'],
    },
    {
      id: 'orchestrator/tool_parser.py',
      name: 'tool_parser.py',
      title: 'Streaming XML & JSON Repair',
      icon: Cpu,
      badge: 'Tool Parser',
      color: 'border-emerald-500/30 bg-emerald-500/5 text-emerald-400',
      description: 'Streaming XML tool tags extractor, non-standard JSON argument repair, and regex heuristics for unescaped newlines.',
      functions: ['StreamingXmlToolParser', 'safe_parse_tool_arguments()', 'clean_user_message()'],
    },
    {
      id: 'orchestrator/client.py',
      name: 'client.py',
      title: 'Onyx / Danswer API Client',
      icon: Activity,
      badge: 'Network Client',
      color: 'border-teal-500/30 bg-teal-500/5 text-teal-400',
      description: 'HTTP connection pooling with urllib3 retries, project file upload, file association, and resilient SSE event streaming.',
      functions: ['stream_chat_response()', 'upload_project_file()', 'attach_file_to_project()'],
    },
    {
      id: 'orchestrator/workspace_sync.py',
      name: 'workspace_sync.py',
      title: 'Two-Stage & Blocking File Sync',
      icon: RefreshCw,
      badge: 'Sync Engine',
      color: 'border-purple-500/30 bg-purple-500/5 text-purple-400',
      description: 'Background async upload+attach callbacks, blocking auto-grounding file sync, local directory listing, and disk readers.',
      functions: ['upload_and_attach_blocking()', 'scan_and_sync_workspace()', 'execute_local_non_read_tool()'],
    },
    {
      id: 'orchestrator/session_store.py',
      name: 'session_store.py',
      title: 'Thread-Safe Session Store',
      icon: Layers,
      badge: 'Session Store',
      color: 'border-amber-500/30 bg-amber-500/5 text-amber-400',
      description: 'Thread-safe conversation registry, multi-turn history tracking, and intelligent summary compaction for handover.',
      functions: ['get_or_create_session()', 'append_turn()', 'generate_handover_summary()'],
    },
    {
      id: 'orchestrator/matrix_manager.py',
      name: 'matrix_manager.py',
      title: 'Dynamic Matrix & Manifests',
      icon: Sparkles,
      badge: 'Routing Matrix',
      color: 'border-rose-500/30 bg-rose-500/5 text-rose-400',
      description: 'Fetches Onyx persona definitions, caches matrix schemas to disk, and injects persona tools into system prompts.',
      functions: ['fetch_persona_matrix()', 'build_routing_manifest()', 'load_cached_matrix()'],
    },
    {
      id: 'orchestrator/core.py',
      name: 'core.py',
      title: 'Orchestrator Coordination Engine',
      icon: Zap,
      badge: 'Core Engine',
      color: 'border-cyan-500/30 bg-cyan-500/5 text-cyan-400',
      description: 'Central pipeline coordinating mode classification, auto-grounding interception, blocking redispatch, and streaming synthesis.',
      functions: ['handle_chat_request()', 'intercept_grounding_tool_batch()', 'redispatch_with_context()'],
    },
    {
      id: 'orchestrator/server.py',
      name: 'server.py',
      title: 'Flask HTTP API & Lifecycles',
      icon: Server,
      badge: 'HTTP Server',
      color: 'border-emerald-500/30 bg-emerald-500/5 text-emerald-400',
      description: 'OpenAI-compatible /v1/chat/completions and /health server with graceful shutdown signal handlers and background session reaper.',
      functions: ['chat_completions()', 'cleanup_active_sessions()', 'run_server()'],
    },
    {
      id: 'app.py',
      name: 'app.py',
      title: 'Main CLI Entrypoint',
      icon: Terminal,
      badge: 'Entrypoint',
      color: 'border-slate-500/30 bg-slate-500/5 text-slate-300',
      description: 'Top-level backward-compatible entrypoint exporting all symbols and launching the production HTTP orchestrator.',
      functions: ['main()', 'run_server(PORT)'],
    },
  ];

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-8 overflow-y-auto">
      {/* Overview Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <Workflow className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                Modular Architecture & Pipeline Dataflow
                <span className="text-xs font-mono font-normal px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  10 Modules
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Refactored from a monolithic 1,200+ line script into strict, decoupled, single-responsibility components.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="px-3 py-1 rounded-lg bg-slate-950 text-slate-300 border border-slate-800 flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              100% Test Coverage
            </span>
          </div>
        </div>

        {/* Dataflow pipeline stages */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2 pt-3 border-t border-slate-800/80 font-mono text-[11px]">
          <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
            <span className="text-slate-500 block mb-1">1. INGESTION</span>
            <span className="text-slate-200 font-medium">server.py / core.py</span>
            <p className="text-[10px] text-slate-400 font-sans mt-0.5">OpenAI JSON parsing & header redaction</p>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
            <span className="text-slate-500 block mb-1">2. ROUTING & SYNC</span>
            <span className="text-slate-200 font-medium">matrix_mgr & workspace_sync</span>
            <p className="text-[10px] text-slate-400 font-sans mt-0.5">Persona routing & 2-stage upload</p>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
            <span className="text-slate-500 block mb-1">3. STREAMING & INTERCEPT</span>
            <span className="text-slate-200 font-medium">tool_parser & core.py</span>
            <p className="text-[10px] text-slate-400 font-sans mt-0.5">XML extraction & blocking auto-sync</p>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
            <span className="text-slate-500 block mb-1">4. DISPATCH / SSE</span>
            <span className="text-slate-200 font-medium">client.py & session_store</span>
            <p className="text-[10px] text-slate-400 font-sans mt-0.5">Onyx streaming & session handover</p>
          </div>
        </div>
      </div>

      {/* Interactive Modules Grid */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <Layers className="w-4 h-4 text-emerald-400" />
          Click any module to open in Workspace Editor
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {modules.map((mod) => {
            const Icon = mod.icon;
            return (
              <button
                key={mod.id}
                onClick={() => onSelectFile(mod.id)}
                className="text-left p-4 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-800 hover:border-emerald-500/50 shadow-sm transition group flex flex-col justify-between space-y-3 cursor-pointer"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className={`p-2 rounded-lg border ${mod.color}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800">
                      {mod.badge}
                    </span>
                  </div>

                  <h4 className="font-semibold text-slate-100 text-sm group-hover:text-emerald-300 font-mono transition flex items-center justify-between">
                    <span>{mod.name}</span>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-emerald-400 transition transform group-hover:translate-x-0.5" />
                  </h4>
                  <div className="text-[11px] font-medium text-slate-400 mt-0.5">{mod.title}</div>

                  <p className="text-xs text-slate-400 leading-relaxed mt-2 font-sans">
                    {mod.description}
                  </p>
                </div>

                <div className="pt-2 border-t border-slate-800/80">
                  <div className="text-[10px] font-mono text-slate-500 mb-1">Key Exports:</div>
                  <div className="flex flex-wrap gap-1">
                    {mod.functions.map((fn, idx) => (
                      <span
                        key={idx}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800/60"
                      >
                        {fn}
                      </span>
                    ))}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
