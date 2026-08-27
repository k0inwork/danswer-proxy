import React, { useState, useMemo } from 'react';
import {
  Folder,
  FolderOpen,
  FileCode2,
  BookOpen,
  Layers,
  Search,
  ChevronRight,
  ChevronDown,
  ShieldCheck,
  Terminal,
  Settings,
  Sparkles,
  FileText,
  FileJson,
  FolderTree,
  ListFilter,
  Check,
  X
} from 'lucide-react';
import { WorkspaceFile, TreeNode, buildDirectoryTree } from '../data/workspaceFiles';

interface FileTreeProps {
  files: WorkspaceFile[];
  activeFileId: string;
  onSelectFile: (fileId: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  modifiedFileIds: Set<string>;
}

export const FileTree: React.FC<FileTreeProps> = ({
  files,
  activeFileId,
  onSelectFile,
  searchQuery,
  onSearchChange,
  modifiedFileIds,
}) => {
  const [viewMode, setViewMode] = useState<'tree' | 'grouped'>('tree');
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

  // Filtered files based on search
  const filteredFiles = useMemo(() => {
    if (!searchQuery.trim()) return files;
    const q = searchQuery.toLowerCase();
    return files.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.path.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.categoryLabel.toLowerCase().includes(q)
    );
  }, [files, searchQuery]);

  const treeData = useMemo(() => {
    return buildDirectoryTree(filteredFiles);
  }, [filteredFiles]);

  const renderFileIcon = (file: WorkspaceFile) => {
    switch (file.icon) {
      case 'python':
        return <FileCode2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
      case 'test':
        return <ShieldCheck className="w-3.5 h-3.5 text-teal-400 shrink-0" />;
      case 'markdown':
        return <BookOpen className="w-3.5 h-3.5 text-indigo-400 shrink-0" />;
      case 'json':
        return <FileJson className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
      case 'typescript':
        return <FileCode2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
      case 'html':
        return <FileText className="w-3.5 h-3.5 text-rose-400 shrink-0" />;
      default:
        return <Settings className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
    }
  };

  const renderTreeNode = (node: TreeNode, depth: number = 0) => {
    if (node.isDirectory) {
      const isExpanded = expandedFolders.has(node.path) || searchQuery.trim().length > 0;
      const childFileCount = countFilesInNode(node);

      return (
        <div key={node.path} className="select-none">
          <button
            onClick={() => toggleFolder(node.path)}
            className="w-full text-left py-1 px-1.5 rounded-md hover:bg-slate-900 text-slate-400 hover:text-slate-200 flex items-center justify-between gap-1.5 transition text-xs font-mono group"
            style={{ paddingLeft: `${depth * 12 + 6}px` }}
          >
            <div className="flex items-center gap-1.5 truncate">
              {isExpanded ? (
                <ChevronDown className="w-3 h-3 text-slate-500 shrink-0" />
              ) : (
                <ChevronRight className="w-3 h-3 text-slate-500 shrink-0" />
              )}
              {isExpanded ? (
                <FolderOpen className="w-3.5 h-3.5 text-amber-400/90 shrink-0" />
              ) : (
                <Folder className="w-3.5 h-3.5 text-amber-400/70 shrink-0" />
              )}
              <span className="truncate font-semibold text-slate-300 group-hover:text-slate-100">
                {node.name}
              </span>
            </div>
            <span className="text-[10px] font-mono text-slate-600 group-hover:text-slate-400 pr-1">
              {childFileCount}
            </span>
          </button>

          {isExpanded && node.children && (
            <div>
              {node.children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    if (node.file) {
      const file = node.file;
      const isActive = activeFileId === file.id;
      const isModified = modifiedFileIds.has(file.id);

      return (
        <button
          key={file.id}
          onClick={() => onSelectFile(file.id)}
          className={`w-full text-left py-1.5 px-2 rounded-md flex items-center justify-between gap-1.5 transition text-xs font-mono group ${
            isActive
              ? 'bg-emerald-500/15 text-emerald-300 font-semibold border border-emerald-500/30'
              : 'text-slate-400 hover:bg-slate-900/80 hover:text-slate-200'
          }`}
          style={{ paddingLeft: `${depth * 12 + 18}px` }}
          title={file.description}
        >
          <div className="flex items-center gap-2 truncate">
            {renderFileIcon(file)}
            <span className="truncate">{file.name}</span>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {isModified && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
            )}
            <span className="text-[10px] text-slate-600 group-hover:text-slate-400 font-mono">
              {file.language}
            </span>
          </div>
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

  // Categorized grouped view
  const categories = [
    { key: 'orchestrator', label: 'Orchestrator Core', icon: FileCode2, color: 'text-emerald-400' },
    { key: 'entrypoint', label: 'Main Entrypoint', icon: Terminal, color: 'text-emerald-400' },
    { key: 'tests', label: 'Unit & Integration Tests', icon: ShieldCheck, color: 'text-teal-400' },
    { key: 'docs', label: 'Architecture & Specs', icon: BookOpen, color: 'text-indigo-400' },
    { key: 'config', label: 'Build & Project Configs', icon: Settings, color: 'text-slate-400' },
  ];

  return (
    <div className="h-full flex flex-col bg-slate-950 select-none">
      {/* Search Header */}
      <div className="p-2.5 border-b border-slate-800/80 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-300 uppercase tracking-wider">
            <FolderTree className="w-4 h-4 text-emerald-400" />
            <span>Workspace Explorer</span>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
            {files.length} files
          </span>
        </div>

        {/* Search Input */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Filter files (e.g. sync, test, client)..."
            className="w-full pl-8 pr-7 py-1 bg-slate-900 border border-slate-800 focus:border-emerald-500/60 rounded-md text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* View Mode Switcher & Quick Actions */}
        <div className="flex items-center justify-between text-[11px] font-mono pt-1 text-slate-400">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setViewMode('tree')}
              className={`px-2 py-0.5 rounded ${
                viewMode === 'tree' ? 'bg-slate-800 text-emerald-400 font-semibold' : 'hover:text-slate-200'
              }`}
            >
              Tree
            </button>
            <button
              onClick={() => setViewMode('grouped')}
              className={`px-2 py-0.5 rounded ${
                viewMode === 'grouped' ? 'bg-slate-800 text-emerald-400 font-semibold' : 'hover:text-slate-200'
              }`}
            >
              Modules
            </button>
          </div>

          {viewMode === 'tree' && (
            <div className="flex items-center gap-1.5">
              <button
                onClick={expandAll}
                className="hover:text-slate-200 text-[10px] text-slate-500 hover:underline"
              >
                Expand
              </button>
              <span className="text-slate-700">•</span>
              <button
                onClick={collapseAll}
                className="hover:text-slate-200 text-[10px] text-slate-500 hover:underline"
              >
                Collapse
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tree / Grouped Content */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {filteredFiles.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-500 font-mono">
            No files matching "{searchQuery}"
          </div>
        ) : viewMode === 'tree' ? (
          <div className="space-y-0.5">{treeData.map((node) => renderTreeNode(node, 0))}</div>
        ) : (
          <div className="space-y-3">
            {categories.map((cat) => {
              const catFiles = filteredFiles.filter((f) => f.category === cat.key);
              if (catFiles.length === 0) return null;
              const Icon = cat.icon;

              return (
                <div key={cat.key} className="space-y-1">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider px-2 pt-1 font-semibold flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Icon className={`w-3 h-3 ${cat.color}`} />
                      {cat.label}
                    </span>
                    <span className="font-mono text-slate-600">{catFiles.length}</span>
                  </div>

                  {catFiles.map((file) => {
                    const isActive = activeFileId === file.id;
                    const isModified = modifiedFileIds.has(file.id);

                    return (
                      <button
                        key={file.id}
                        onClick={() => onSelectFile(file.id)}
                        className={`w-full text-left py-1.5 px-2.5 rounded-md flex items-center justify-between gap-2 transition text-xs font-mono ${
                          isActive
                            ? 'bg-emerald-500/15 text-emerald-300 font-semibold border border-emerald-500/30'
                            : 'text-slate-300 hover:bg-slate-900 hover:text-slate-100'
                        }`}
                        title={file.description}
                      >
                        <div className="flex items-center gap-2 truncate">
                          {renderFileIcon(file)}
                          <span className="truncate">{file.name}</span>
                        </div>
                        {isModified && (
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0"></span>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
