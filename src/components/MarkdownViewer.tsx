import React from 'react';
import { BookOpen, FileText, CheckCircle2, ListTree, Code2 } from 'lucide-react';

interface MarkdownViewerProps {
  content: string;
  filename: string;
}

export const MarkdownViewer: React.FC<MarkdownViewerProps> = ({ content, filename }) => {
  // Parse markdown lines into formatted blocks for rich preview
  const renderFormattedMarkdown = (raw: string) => {
    const lines = raw.split('\n');
    const elements: React.ReactNode[] = [];
    let inCodeBlock = false;
    let codeBlockContent: string[] = [];
    let codeBlockLang = '';
    let inTable = false;
    let tableRows: string[][] = [];

    const flushCodeBlock = (key: number) => {
      if (codeBlockContent.length > 0) {
        elements.push(
          <div key={`code-${key}`} className="my-4 rounded-xl overflow-hidden border border-slate-800 bg-slate-950 font-mono text-xs shadow-md">
            {codeBlockLang && (
              <div className="px-3.5 py-1.5 bg-slate-900 border-b border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
                <span>{codeBlockLang}</span>
                <span className="text-[10px] text-slate-500 font-sans">Snippet</span>
              </div>
            )}
            <pre className="p-4 text-emerald-300 overflow-x-auto leading-relaxed">
              <code>{codeBlockContent.join('\n')}</code>
            </pre>
          </div>
        );
        codeBlockContent = [];
        codeBlockLang = '';
      }
    };

    const flushTable = (key: number) => {
      if (tableRows.length > 0) {
        const header = tableRows[0];
        const rows = tableRows.slice(1);
        elements.push(
          <div key={`table-${key}`} className="my-4 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-200 uppercase font-mono text-[11px] border-b border-slate-800">
                <tr>
                  {header.map((col, cIdx) => (
                    <th key={cIdx} className="px-4 py-2.5 font-semibold">
                      {col.trim()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {rows.map((row, rIdx) => (
                  <tr key={rIdx} className="hover:bg-slate-900/40 transition">
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} className="px-4 py-2.5 font-mono text-xs">
                        {cell.trim()}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        tableRows = [];
        inTable = false;
      }
    };

    lines.forEach((line, idx) => {
      // Code blocks
      if (line.startsWith('```')) {
        if (inCodeBlock) {
          inCodeBlock = false;
          flushCodeBlock(idx);
        } else {
          if (inTable) flushTable(idx);
          inCodeBlock = true;
          codeBlockLang = line.replace('```', '').trim();
        }
        return;
      }

      if (inCodeBlock) {
        codeBlockContent.push(line);
        return;
      }

      // Tables
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        // Skip separator row (|---|---|)
        if (line.includes('---')) {
          inTable = true;
          return;
        }
        const cols = line.split('|').slice(1, -1);
        tableRows.push(cols);
        return;
      } else if (inTable) {
        flushTable(idx);
      }

      // Headings
      if (line.startsWith('# ')) {
        elements.push(
          <h1 key={idx} className="text-xl sm:text-2xl font-bold text-slate-100 mt-6 mb-3 pb-2 border-b border-slate-800 flex items-center gap-2">
            <span className="w-1.5 h-6 bg-emerald-500 rounded-full inline-block"></span>
            {line.replace('# ', '')}
          </h1>
        );
        return;
      }
      if (line.startsWith('## ')) {
        elements.push(
          <h2 key={idx} className="text-lg sm:text-xl font-semibold text-slate-100 mt-5 mb-2.5 pb-1 border-b border-slate-800/60 flex items-center gap-2">
            <span className="w-1 h-4 bg-indigo-500 rounded-full inline-block"></span>
            {line.replace('## ', '')}
          </h2>
        );
        return;
      }
      if (line.startsWith('### ')) {
        elements.push(
          <h3 key={idx} className="text-sm sm:text-base font-semibold text-emerald-300 mt-4 mb-2 flex items-center gap-1.5">
            <ListTree className="w-4 h-4 text-emerald-400" />
            {line.replace('### ', '')}
          </h3>
        );
        return;
      }

      // Blockquotes
      if (line.startsWith('> ')) {
        elements.push(
          <div key={idx} className="my-3 pl-3.5 py-1.5 border-l-2 border-amber-500/80 bg-amber-500/5 rounded-r-lg text-xs text-amber-200/90 font-mono">
            {line.replace('> ', '')}
          </div>
        );
        return;
      }

      // Bullet lists
      if (line.startsWith('- ') || line.startsWith('* ')) {
        const itemText = line.substring(2);
        elements.push(
          <div key={idx} className="flex items-start gap-2 text-xs sm:text-sm text-slate-300 my-1 pl-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-2 shrink-0"></span>
            <div className="flex-1 leading-relaxed">
              {formatInlineStyles(itemText)}
            </div>
          </div>
        );
        return;
      }

      // Numbered lists
      const numMatch = line.match(/^(\d+)\.\s+(.*)/);
      if (numMatch) {
        elements.push(
          <div key={idx} className="flex items-start gap-2.5 text-xs sm:text-sm text-slate-300 my-1 pl-2">
            <span className="text-[11px] font-mono font-bold text-indigo-400 bg-indigo-500/10 px-1.5 py-0.2 rounded border border-indigo-500/20 shrink-0">
              {numMatch[1]}
            </span>
            <div className="flex-1 leading-relaxed font-sans">
              {formatInlineStyles(numMatch[2])}
            </div>
          </div>
        );
        return;
      }

      // Empty line
      if (!line.trim()) {
        elements.push(<div key={idx} className="h-2" />);
        return;
      }

      // Regular paragraph
      elements.push(
        <p key={idx} className="text-xs sm:text-sm text-slate-300 leading-relaxed my-1.5">
          {formatInlineStyles(line)}
        </p>
      );
    });

    if (inCodeBlock) flushCodeBlock(lines.length);
    if (inTable) flushTable(lines.length);

    return elements;
  };

  const formatInlineStyles = (text: string) => {
    // Simple inline formatting for bold, backticks, links
    const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
    return parts.map((part, pIdx) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={pIdx} className="bg-slate-900 text-emerald-300 px-1.5 py-0.5 rounded font-mono text-[11px] border border-slate-800">
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={pIdx} className="text-slate-100 font-semibold">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return part;
    });
  };

  return (
    <div className="p-6 sm:p-8 max-w-4xl mx-auto space-y-2 overflow-y-auto">
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between mb-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100 text-sm">{filename}</h3>
            <p className="text-xs text-slate-400">Formatted documentation & specification reader</p>
          </div>
        </div>
        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
          Markdown Rendered
        </span>
      </div>

      <div className="bg-slate-950/60 border border-slate-800/80 rounded-2xl p-6 sm:p-8 shadow-inner font-sans">
        {renderFormattedMarkdown(content)}
      </div>
    </div>
  );
};
