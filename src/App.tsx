import React, { useState, useMemo, useRef, useEffect } from 'react';
import {
  FolderTree,
  FileCode2,
  BookOpen,
  Search,
  Copy,
  Check,
  Download,
  WrapText,
  ZoomIn,
  ZoomOut,
  X,
  ChevronUp,
  ChevronDown,
  Archive,
  Terminal,
  ShieldCheck,
  Eye,
  EyeOff,
  Filter,
  CheckCircle2
} from 'lucide-react';
import { WORKSPACE_FILES, WorkspaceFile } from './data/workspaceFiles';
import { PythonFileTree } from './components/PythonFileTree';
import { MarkdownViewer } from './components/MarkdownViewer';
import { RepoFile, downloadRepoAsZip } from './utils/zipUtils';

export default function App() {
  // Selected file state
  const [activeFileId, setActiveFileId] = useState<string>('orchestrator/workspace_sync.py');
  const [onlyPython, setOnlyPython] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>('');
  
  // In-file search state
  const [fileSearchQuery, setFileSearchQuery] = useState<string>('');
  const [showFileSearch, setShowFileSearch] = useState<boolean>(false);
  const [activeMatchIndex, setActiveMatchIndex] = useState<number>(0);

  // UI settings
  const [copied, setCopied] = useState<boolean>(false);
  const [copiedPath, setCopiedPath] = useState<boolean>(false);
  const [wrapLines, setWrapLines] = useState<boolean>(false);
  const [fontSize, setFontSize] = useState<number>(13);
  const [isDownloadingZip, setIsDownloadingZip] = useState<boolean>(false);
  const [renderedMarkdownMode, setRenderedMarkdownMode] = useState<boolean>(true);
  const [zipSuccessToast, setZipSuccessToast] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineNumbersRef = useRef<HTMLDivElement>(null);
  const fileSearchInputRef = useRef<HTMLInputElement>(null);

  // Active file object
  const activeFile: WorkspaceFile = useMemo(() => {
    return WORKSPACE_FILES.find((f) => f.id === activeFileId) || WORKSPACE_FILES[0];
  }, [activeFileId]);

  const currentContent = activeFile.initialContent;
  const lines = useMemo(() => currentContent.split('\n'), [currentContent]);
  const fileSizeKB = (new Blob([currentContent]).size / 1024).toFixed(1);

  // Search matches within active file
  const searchMatches = useMemo(() => {
    if (!fileSearchQuery.trim()) return [];
    const matches: { index: number; line: number; ch: number }[] = [];
    const q = fileSearchQuery.toLowerCase();
    const textLower = currentContent.toLowerCase();
    let pos = 0;
    while ((pos = textLower.indexOf(q, pos)) !== -1) {
      const lineNum = currentContent.substring(0, pos).split('\n').length;
      const lastNewline = currentContent.lastIndexOf('\n', pos);
      const chNum = pos - (lastNewline === -1 ? 0 : lastNewline + 1) + 1;
      matches.push({ index: pos, line: lineNum, ch: chNum });
      pos += q.length;
    }
    return matches;
  }, [currentContent, fileSearchQuery]);

  useEffect(() => {
    if (activeMatchIndex >= searchMatches.length) {
      setActiveMatchIndex(0);
    }
  }, [searchMatches.length, activeMatchIndex]);

  const handleScroll = () => {
    if (textareaRef.current && lineNumbersRef.current) {
      lineNumbersRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  };

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(currentContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = currentContent;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCopyPath = async () => {
    try {
      await navigator.clipboard.writeText(activeFile.path);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
    } catch {
      // fallback
    }
  };

  const handleDownloadSingleFile = () => {
    const blob = new Blob([currentContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = activeFile.name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadZip = async () => {
    setIsDownloadingZip(true);
    try {
      // Collect files based on onlyPython filter or all
      const targetFiles = onlyPython
        ? WORKSPACE_FILES.filter((f) => f.language === 'Python' || f.name.endsWith('.py') || f.name.endsWith('.md'))
        : WORKSPACE_FILES;

      const repoFiles: RepoFile[] = targetFiles.map((f) => ({
        path: f.path,
        content: f.initialContent,
      }));

      const filename = onlyPython
        ? 'python-orchestrator-modules.zip'
        : 'danswer-onyx-orchestrator-full.zip';

      await downloadRepoAsZip(repoFiles, filename);
      setZipSuccessToast(`Successfully downloaded ${repoFiles.length} files as ${filename}!`);
      setTimeout(() => setZipSuccessToast(null), 4000);
    } catch (err) {
      console.error('ZIP generation failed:', err);
    } finally {
      setIsDownloadingZip(false);
    }
  };

  const jumpToMatch = (matchIdx: number) => {
    if (!searchMatches.length || !textareaRef.current) return;
    const match = searchMatches[matchIdx];
    textareaRef.current.focus();
    textareaRef.current.setSelectionRange(match.index, match.index + fileSearchQuery.length);
    setActiveMatchIndex(matchIdx);

    const approxLineHeight = fontSize * 1.5;
    textareaRef.current.scrollTop = Math.max(0, (match.line - 5) * approxLineHeight);
  };

  const handleNextMatch = () => {
    if (!searchMatches.length) return;
    const nextIdx = (activeMatchIndex + 1) % searchMatches.length;
    jumpToMatch(nextIdx);
  };

  const handlePrevMatch = () => {
    if (!searchMatches.length) return;
    const prevIdx = (activeMatchIndex - 1 + searchMatches.length) % searchMatches.length;
    jumpToMatch(prevIdx);
  };

  const pythonFilesCount = WORKSPACE_FILES.filter((f) => f.language === 'Python' || f.name.endsWith('.py')).length;
  const totalLoc = WORKSPACE_FILES.reduce((acc, f) => acc + f.initialContent.split('\n').length, 0);

  return (
    <div className="h-screen w-full flex flex-col bg-slate-950 text-slate-100 font-sans select-none overflow-hidden">
      {/* Toast Notification */}
      {zipSuccessToast && (
        <div className="absolute top-14 right-6 z-50 bg-emerald-600 text-white px-4 py-2.5 rounded-xl shadow-lg flex items-center gap-2 text-xs font-medium">
          <CheckCircle2 className="w-4 h-4" />
          <span>{zipSuccessToast}</span>
        </div>
      )}

      {/* Main Top Header */}
      <header className="h-14 bg-slate-900 border-b border-slate-800 px-4 flex items-center justify-between shrink-0 z-20">
        {/* Left App Logo & Title */}
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <FileCode2 className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-sm sm:text-base text-slate-100 tracking-tight font-mono">
                Python Files Tree & Viewer
              </h1>
              <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                {pythonFilesCount} .py modules • {totalLoc.toLocaleString()} LOC
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              Clean modular Python orchestrator codebase with instant ZIP download.
            </p>
          </div>
        </div>

        {/* Right Top Actions */}
        <div className="flex items-center gap-2">
          {/* Quick Copy File Content */}
          <button
            onClick={handleCopyCode}
            title="Copy current file code"
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
            <span className="hidden sm:inline">{copied ? 'Copied!' : 'Copy Code'}</span>
          </button>

          {/* Download Single File */}
          <button
            onClick={handleDownloadSingleFile}
            title={`Download ${activeFile.name}`}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition"
          >
            <Download className="w-3.5 h-3.5 text-indigo-400" />
            <span className="hidden sm:inline">Download {activeFile.name}</span>
          </button>

          {/* Primary Download All ZIP button */}
          <button
            onClick={handleDownloadZip}
            disabled={isDownloadingZip}
            title="Download full python files tree as ZIP archive"
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md flex items-center gap-2 transition disabled:opacity-50"
          >
            <Archive className={`w-4 h-4 ${isDownloadingZip ? 'animate-bounce' : ''}`} />
            <span>{isDownloadingZip ? 'Preparing ZIP...' : 'Download Full ZIP'}</span>
          </button>
        </div>
      </header>

      {/* In-File Search Bar (Ctrl+F) */}
      {showFileSearch && (
        <div className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center justify-between gap-3 text-xs shadow-md z-10">
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                ref={fileSearchInputRef}
                type="text"
                value={fileSearchQuery}
                onChange={(e) => setFileSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    if (e.shiftKey) handlePrevMatch();
                    else handleNextMatch();
                  }
                  if (e.key === 'Escape') setShowFileSearch(false);
                }}
                placeholder={`Find text in ${activeFile.name}...`}
                className="w-full pl-8 pr-3 py-1 bg-slate-950 border border-slate-700 rounded text-slate-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
              />
            </div>
            {fileSearchQuery && (
              <span className="text-[11px] text-slate-400 font-mono whitespace-nowrap">
                {searchMatches.length === 0
                  ? 'No matches'
                  : `${activeMatchIndex + 1} of ${searchMatches.length}`}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={handlePrevMatch}
              disabled={searchMatches.length === 0}
              className="p-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 rounded border border-slate-700"
              title="Previous Match"
            >
              <ChevronUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleNextMatch}
              disabled={searchMatches.length === 0}
              className="p-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 rounded border border-slate-700"
              title="Next Match"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setShowFileSearch(false)}
              className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded ml-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Main Workspace Body */}
      <div className="flex-1 flex min-h-0 min-w-0 overflow-hidden bg-slate-950">
        {/* Left Side: Python File Tree Explorer */}
        <aside className="w-80 bg-slate-950 flex flex-col shrink-0 min-h-0">
          <PythonFileTree
            files={WORKSPACE_FILES}
            activeFileId={activeFileId}
            onSelectFile={(id) => setActiveFileId(id)}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onlyPython={onlyPython}
            onToggleOnlyPython={setOnlyPython}
            onDownloadAllZip={handleDownloadZip}
            isDownloadingZip={isDownloadingZip}
          />
        </aside>

        {/* Right Side: Code Viewer */}
        <main className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden bg-slate-950">
          {/* File Header Bar */}
          <div className="h-10 bg-slate-900 border-b border-slate-800 px-4 flex items-center justify-between shrink-0 select-none">
            {/* Breadcrumbs & Copy Path */}
            <div className="flex items-center gap-2 truncate">
              <span className="text-slate-500 font-mono text-xs">workspace /</span>
              <span className="font-mono text-xs font-semibold text-emerald-300 truncate">
                {activeFile.path}
              </span>
              <button
                onClick={handleCopyPath}
                title="Copy relative file path"
                className="p-1 hover:bg-slate-800 text-slate-500 hover:text-slate-300 rounded"
              >
                {copiedPath ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              </button>
            </div>

            {/* Viewer Controls */}
            <div className="flex items-center gap-2 font-mono text-xs text-slate-400">
              {/* Markdown Toggle */}
              {activeFile.icon === 'markdown' && (
                <button
                  onClick={() => setRenderedMarkdownMode(!renderedMarkdownMode)}
                  className={`px-2 py-0.5 rounded text-xs flex items-center gap-1 border transition ${
                    renderedMarkdownMode
                      ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  {renderedMarkdownMode ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                  <span>{renderedMarkdownMode ? 'Rendered' : 'Raw'}</span>
                </button>
              )}

              {/* In-File Find Button */}
              <button
                onClick={() => {
                  setShowFileSearch(!showFileSearch);
                  if (!showFileSearch) setTimeout(() => fileSearchInputRef.current?.focus(), 50);
                }}
                className={`p-1 rounded border transition ${
                  showFileSearch
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200 border-slate-700'
                }`}
                title="Search in file"
              >
                <Search className="w-3.5 h-3.5" />
              </button>

              {/* Line Wrap Toggle */}
              <button
                onClick={() => setWrapLines(!wrapLines)}
                className={`p-1 rounded border transition ${
                  wrapLines
                    ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200 border-slate-700'
                }`}
                title="Toggle line wrap"
              >
                <WrapText className="w-3.5 h-3.5" />
              </button>

              {/* Font Zoom */}
              <div className="flex items-center gap-1 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700">
                <button
                  onClick={() => setFontSize((f) => Math.max(10, f - 1))}
                  className="hover:text-slate-200"
                  title="Decrease font size"
                >
                  <ZoomOut className="w-3 h-3" />
                </button>
                <span className="text-[10px] text-slate-400">{fontSize}px</span>
                <button
                  onClick={() => setFontSize((f) => Math.min(22, f + 1))}
                  className="hover:text-slate-200"
                  title="Increase font size"
                >
                  <ZoomIn className="w-3 h-3" />
                </button>
              </div>

              {/* File Info Pills */}
              <span className="text-[11px] text-slate-500 hidden md:inline">
                {lines.length} lines • {fileSizeKB} KB
              </span>
            </div>
          </div>

          {/* Description banner */}
          <div className="px-4 py-1.5 bg-slate-900/40 border-b border-slate-900 text-xs text-slate-400 flex items-center justify-between">
            <span className="truncate">{activeFile.description}</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
              {activeFile.language}
            </span>
          </div>

          {/* Code Viewer or Markdown Reader */}
          {activeFile.icon === 'markdown' && renderedMarkdownMode ? (
            <div className="flex-1 min-h-0 min-w-0 overflow-auto bg-slate-950">
              <MarkdownViewer content={currentContent} filename={activeFile.name} />
            </div>
          ) : (
            <div className="flex-1 min-h-0 min-w-0 relative flex overflow-hidden bg-slate-950">
              {/* Line Numbers */}
              <div
                ref={lineNumbersRef}
                aria-hidden="true"
                className="w-14 sm:w-16 bg-slate-950/90 border-r border-slate-800 select-none py-3 text-right pr-3 font-mono text-slate-600 overflow-hidden shrink-0"
                style={{ fontSize: `${fontSize}px`, lineHeight: 1.5 }}
              >
                {lines.map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>

              {/* Code Display Textarea */}
              <textarea
                ref={textareaRef}
                value={currentContent}
                readOnly
                onScroll={handleScroll}
                wrap={wrapLines ? 'soft' : 'off'}
                spellCheck={false}
                className="flex-1 w-full h-full p-3 font-mono text-slate-200 bg-transparent resize-none focus:outline-none selection:bg-emerald-500/30 selection:text-emerald-200 overflow-auto"
                style={{
                  fontSize: `${fontSize}px`,
                  lineHeight: 1.5,
                  tabSize: 4,
                }}
              />
            </div>
          )}
        </main>
      </div>

      {/* Bottom Status Bar */}
      <footer className="h-6 bg-slate-900 border-t border-slate-800 px-4 flex items-center justify-between text-[11px] font-mono text-slate-400 shrink-0 select-none">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 text-slate-300 truncate">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block animate-pulse"></span>
            {activeFile.path}
          </span>
          <span>{lines.length} lines</span>
          <span>{fileSizeKB} KB</span>
        </div>

        <div className="flex items-center gap-4">
          <span className="hidden sm:inline">UTF-8</span>
          <span className="text-emerald-400 font-semibold">{activeFile.language}</span>
        </div>
      </footer>
    </div>
  );
}
