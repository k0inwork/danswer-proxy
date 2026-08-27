import React, { useState, useMemo } from 'react';
import {
  Folder,
  FolderOpen,
  FileCode2,
  BookOpen,
  Search,
  ChevronRight,
  ChevronDown,
  ShieldCheck,
  Terminal,
  Settings,
  Download,
  Check,
  Copy,
  Filter,
  X
} from 'lucide-react';
import { WorkspaceFile, TreeNode, buildDirectoryTree } from '../data/workspaceFiles';

interface PythonFileTreeProps {
  files: WorkspaceFile[];
  activeFileId: string;
  onSelectFile: (fileId: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onlyPython: boolean;
  onToggleOnlyPython: (val: boolean) => void;
  onDownloadAllZip: () => void;
  isDownloadingZip: boolean;
}

export const PythonFileTree: React.FC<PythonFileTreeProps> = ({
  files,
  activeFileId,
  onSelectFile,
  searchQuery,
  onSearchChange,
  onlyPython,
  onToggleOnlyPython,
  onDownloadAllZip,
  isDownloadingZip,
}) => {
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set(['orchestrator', 'tests', 'tests/unit', 'tests/integration', 'doc'])
  );

  const toggleFolder = (folderPath: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedFolders(new Set(['orchestrator', 'tests', 'tests/unit', 'tests/integration', 'doc', 'config']));
  };

  const collapseAll = () => {
    setExpandedFolders(new Set());
  };

  // Filtered files
  const filteredFiles = useMemo(() => {
    let list = files;
    if (onlyPython) {
      list = list.filter((f) => f.language === 'Python' || f.name.endsWith('.py'));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.path.toLowerCase().includes(q) ||
          f.description.toLowerCase().includes(q)
      );
    }
    return list;
  }, [files, onlyPython, searchQuery]);

  const treeData = useMemo(() => {
    return buildDirectoryTree(filteredFiles);
  }, [filteredFiles]);

  const renderFileIcon = (file: WorkspaceFile) => {
    if (file.language === 'Python' || file.name.endsWith('.py')) {
      if (file.category === 'tests') {
        return <ShieldCheck className="w-4 h-4 text-teal-400 shrink-0" />;
      }
      if (file.id === 'app.py') {
        return <Terminal className="w-4 h-4 text-emerald-400 shrink-0" />;
      }
      return <FileCode2 className="w-4 h-4 text-emerald-400 shrink-0" />;
    }
    if (file.name.endsWith('.md')) {
      return <BookOpen className="w-4 h-4 text-indigo-400 shrink-0" />;
    }
    return <Settings className="w-4 h-4 text-slate-400 shrink-0" />;
  };

  const renderTreeNode = (node: TreeNode, depth: number = 0) => {
    if (node.isDirectory) {
      const isExpanded = expandedFolders.has(node.path) || searchQuery.trim().length > 0;
      const count = countFilesInNode(node);

      return (
        <div key={node.path} className="select-none">
          <button
            onClick={() => toggleFolder(node.path)}
            className="w-full text-left py-1.5 px-2 rounded-lg hover:bg-slate-900 text-slate-400 hover:text-slate-200 flex items-center justify-between gap-1.5 transition text-xs font-mono group"
            style={{ paddingLeft: `${depth * 14 + 8}px` }}
          >
            <div className="flex items-center gap-2 truncate">
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              )}
              {isExpanded ? (
                <FolderOpen className="w-4 h-4 text-amber-400/90 shrink-0" />
              ) : (
                <Folder className="w-4 h-4 text-amber-400/70 shrink-0" />
              )}
              <span className="truncate font-semibold text-slate-200 group-hover:text-white">
                {node.name}/
              </span>
            </div>
            <span className="text-[10px] font-mono text-slate-500 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
              {count}
            </span>
          </button>

          {isExpanded && node.children && (
            <div className="space-y-0.5">
              {node.children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    if (node.file) {
      const file = node.file;
      const isActive = activeFileId === file.id;

      return (
        <button
          key={file.id}
          onClick={() => onSelectFile(file.id)}
          className={`w-full text-left py-1.5 px-2 rounded-lg flex items-center justify-between gap-2 transition text-xs font-mono group ${
            isActive
              ? 'bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/40 shadow-xs'
              : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
          }`}
          style={{ paddingLeft: `${depth * 14 + 20}px` }}
          title={file.description}
        >
          <div className="flex items-center gap-2 truncate">
            {renderFileIcon(file)}
            <span className="truncate">{file.name}</span>
          </div>

          <span className="text-[10px] text-slate-500 group-hover:text-slate-400 font-mono shrink-0">
            {file.initialContent.split('\n').length} lines
          </span>
        </button>
      );
    }

    return null;
  };

  function countFilesInNode(node: TreeNode): number {
    if (!node.isDirectory) return 1;
    if (!node.children) return 0;
    return node.children.reduce((acc, c) => acc + countFilesInNode(c), 0);
  }

  const pythonCount = files.filter((f) => f.language === 'Python' || f.name.endsWith('.py')).length;

  return (
    <div className="h-full flex flex-col bg-slate-950 select-none border-r border-slate-800">
      {/* Top Controls */}
      <div className="p-3 border-b border-slate-800 space-y-2.5 bg-slate-900/60">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></div>
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono">
              Files Tree
            </span>
          </div>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-950 text-emerald-400 border border-slate-800">
            {pythonCount} Python files
          </span>
        </div>

        {/* Search Filter */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search .py files..."
            className="w-full pl-8 pr-7 py-1.5 bg-slate-950 border border-slate-800 focus:border-emerald-500 rounded-lg text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Python Toggle & Expand/Collapse */}
        <div className="flex items-center justify-between text-xs pt-0.5">
          <button
            onClick={() => onToggleOnlyPython(!onlyPython)}
            className={`px-2 py-1 rounded-md text-[11px] font-mono flex items-center gap-1.5 transition ${
              onlyPython
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
            }`}
          >
            <Filter className="w-3 h-3" />
            <span>{onlyPython ? 'Python (.py) Only' : 'All Files'}</span>
          </button>

          <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500">
            <button onClick={expandAll} className="hover:text-slate-300">
              Expand
            </button>
            <span>/</span>
            <button onClick={collapseAll} className="hover:text-slate-300">
              Collapse
            </button>
          </div>
        </div>
      </div>

      {/* Tree View */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {filteredFiles.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-500 font-mono">
            No files found matching "{searchQuery}"
          </div>
        ) : (
          treeData.map((node) => renderTreeNode(node, 0))
        )}
      </div>

      {/* Sidebar Footer: ZIP Download Action */}
      <div className="p-3 border-t border-slate-800 bg-slate-900/80 space-y-2">
        <button
          onClick={onDownloadAllZip}
          disabled={isDownloadingZip}
          className="w-full py-2.5 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-sm transition disabled:opacity-50"
        >
          <Download className={`w-4 h-4 ${isDownloadingZip ? 'animate-bounce' : ''}`} />
          <span>{isDownloadingZip ? 'Archiving ZIP...' : 'Download Python Tree (.zip)'}</span>
        </button>
      </div>
    </div>
  );
};
