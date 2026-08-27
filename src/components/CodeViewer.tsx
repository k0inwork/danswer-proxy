import React, { useState, useMemo } from 'react';
import { Search, Copy, Check, Download, ArrowDownCircle, Code2 } from 'lucide-react';
import { APP4_PYTHON_SOURCE } from '../data/rawPythonSource';

export const CodeViewer: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [copied, setCopied] = useState(false);

  const lines = useMemo(() => APP4_PYTHON_SOURCE.split('\n'), []);

  const filteredLines = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return lines
      .map((text, idx) => ({ lineNum: idx + 1, text }))
      .filter((item) => item.text.toLowerCase().includes(q));
  }, [lines, searchQuery]);

  const handleCopy = () => {
    navigator.clipboard.writeText(APP4_PYTHON_SOURCE);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([APP4_PYTHON_SOURCE], { type: 'text/x-python' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'app4.py';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const scrollToAnchor = (lineTarget: number) => {
    const el = document.getElementById(`code-line-${lineTarget}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('bg-emerald-950/70', 'ring-1', 'ring-emerald-500');
      setTimeout(() => {
        el.classList.remove('bg-emerald-950/70', 'ring-1', 'ring-emerald-500');
      }, 2500);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Banner with Quick Jumps */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase text-slate-400 tracking-wider flex items-center gap-1">
            <ArrowDownCircle className="w-3.5 h-3.5 text-emerald-400" />
            Quick Jumps:
          </span>
          <button
            onClick={() => scrollToAnchor(1)}
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
          >
            📋 Header Changelog
          </button>
          <button
            onClick={() => scrollToAnchor(190)}
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-emerald-300 rounded border border-slate-700 transition"
          >
            ⚡ safe_parse_tool_arguments()
          </button>
          <button
            onClick={() => scrollToAnchor(280)}
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-blue-300 rounded border border-slate-700 transition"
          >
            ✂️ extract_last_tool_execution_context()
          </button>
          <button
            onClick={() => scrollToAnchor(235)}
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-amber-300 rounded border border-slate-700 transition"
          >
            📡 StreamingXmlToolParser
          </button>
          <button
            onClick={() => scrollToAnchor(340)}
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-purple-300 rounded border border-slate-700 transition"
          >
            🔄 HTTP Retry Adapter
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative w-full md:w-64">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search code..."
            className="w-full pl-8 pr-3 py-1.5 bg-slate-950 text-slate-200 border border-slate-800 rounded-lg text-xs focus:outline-none focus:border-emerald-500 transition"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-slate-500 hover:text-slate-300"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Code Container */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="bg-slate-900/90 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Code2 className="w-4 h-4 text-emerald-400" />
            <span className="font-mono text-xs font-semibold text-slate-200">
              app4.py (Enhanced Danswer / Onyx LLM Proxy)
            </span>
            <span className="text-xs text-slate-400 font-mono">
              ({lines.length} lines · ~26 KB)
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="px-2.5 py-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded border border-slate-700 transition flex items-center gap-1"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied' : 'Copy All'}</span>
            </button>
            <button
              onClick={handleDownload}
              className="px-2.5 py-1 text-xs text-emerald-300 hover:text-emerald-200 bg-emerald-950/60 hover:bg-emerald-900/80 rounded border border-emerald-800/80 transition flex items-center gap-1"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Save File</span>
            </button>
          </div>
        </div>

        {/* Filtered search results view if searching */}
        {filteredLines ? (
          <div className="p-4 max-h-[700px] overflow-y-auto font-mono text-xs text-slate-300 divide-y divide-slate-800/60">
            <div className="text-slate-400 text-xs mb-3">
              Found <span className="text-emerald-400 font-bold">{filteredLines.length}</span> matching lines for "{searchQuery}":
            </div>
            {filteredLines.length === 0 ? (
              <div className="py-8 text-center text-slate-500">No matching lines found.</div>
            ) : (
              filteredLines.map((item) => (
                <div
                  key={item.lineNum}
                  onClick={() => {
                    setSearchQuery('');
                    setTimeout(() => scrollToAnchor(item.lineNum), 100);
                  }}
                  className="py-1.5 px-2 hover:bg-slate-900/80 cursor-pointer rounded flex gap-4 transition"
                >
                  <span className="text-slate-500 w-12 shrink-0 select-none text-right">
                    {item.lineNum}
                  </span>
                  <span className="text-slate-200 break-all">{item.text}</span>
                </div>
              ))
            )}
          </div>
        ) : (
          /* Normal line-by-line full code view */
          <div className="p-4 max-h-[750px] overflow-y-auto font-mono text-xs text-slate-300 leading-relaxed select-text">
            <table className="w-full border-collapse">
              <tbody>
                {lines.map((line, idx) => {
                  const lineNum = idx + 1;
                  const isComment = line.trim().startsWith('#') || line.trim().startsWith('"""') || line.trim().startsWith('*') || line.trim().startsWith('==') || line.trim().startsWith('--');
                  const isChangelogHeader = lineNum >= 2 && lineNum <= 45;
                  const isFunction = line.trim().startsWith('def ') || line.trim().startsWith('class ');
                  const isImportantFunc = line.includes('def safe_parse_tool_arguments') || line.includes('def extract_last_tool_execution_context') || line.includes('class StreamingXmlToolParser') || line.includes('def clean_user_message');

                  return (
                    <tr
                      key={lineNum}
                      id={`code-line-${lineNum}`}
                      className={`hover:bg-slate-900/60 transition-colors ${
                        isImportantFunc ? 'bg-emerald-950/30' : ''
                      }`}
                    >
                      <td className="w-12 text-slate-600 text-right pr-4 select-none align-top font-mono text-[11px]">
                        {lineNum}
                      </td>
                      <td
                        className={`whitespace-pre-wrap break-all ${
                          isChangelogHeader
                            ? 'text-emerald-300/90 font-medium'
                            : isComment
                            ? 'text-slate-500 italic'
                            : isFunction
                            ? 'text-amber-300 font-semibold'
                            : 'text-slate-200'
                        }`}
                      >
                        {line || ' '}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
