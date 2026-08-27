/**
 * Generates standard Unified Diff format string for Git patch compatibility.
 */
export interface DiffLine {
  type: 'add' | 'delete' | 'context';
  text: string;
  oldLineNum?: number;
  newLineNum?: number;
}

export interface DiffHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: DiffLine[];
}

export function computeLineDiff(originalText: string, modifiedText: string): {
  unifiedDiff: string;
  additions: number;
  deletions: number;
  hunks: DiffHunk[];
} {
  const oldLines = originalText.split('\n');
  const newLines = modifiedText.split('\n');

  // Simple LCS line diff implementation
  const m = oldLines.length;
  const n = newLines.length;

  // For very large files, limit LCS table size or compute chunks
  const matrix: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));

  for (let i = 0; i < m; i++) {
    for (let j = 0; j < n; j++) {
      if (oldLines[i] === newLines[j]) {
        matrix[i + 1][j + 1] = matrix[i][j] + 1;
      } else {
        matrix[i + 1][j + 1] = Math.max(matrix[i + 1][j], matrix[i][j + 1]);
      }
    }
  }

  // Backtrack to find diff entries
  let i = m;
  let j = n;
  const diffEntries: { type: 'add' | 'delete' | 'same'; text: string; oldIdx?: number; newIdx?: number }[] = [];

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      diffEntries.unshift({ type: 'same', text: oldLines[i - 1], oldIdx: i, newIdx: j });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || matrix[i][j - 1] >= matrix[i - 1][j])) {
      diffEntries.unshift({ type: 'add', text: newLines[j - 1], newIdx: j });
      j--;
    } else if (i > 0 && (j === 0 || matrix[i][j - 1] < matrix[i - 1][j])) {
      diffEntries.unshift({ type: 'delete', text: oldLines[i - 1], oldIdx: i });
      i--;
    }
  }

  let additions = 0;
  let deletions = 0;

  diffEntries.forEach(entry => {
    if (entry.type === 'add') additions++;
    if (entry.type === 'delete') deletions++;
  });

  // Group diff entries into unified diff hunks (with 3 lines of context)
  const contextSize = 3;
  const hunks: DiffHunk[] = [];
  let currentHunkLines: DiffLine[] = [];
  let hunkOldStart = 1;
  let hunkNewStart = 1;
  let hunkOldCount = 0;
  let hunkNewCount = 0;
  let pendingContext: DiffLine[] = [];

  for (let idx = 0; idx < diffEntries.length; idx++) {
    const entry = diffEntries[idx];
    const isChange = entry.type === 'add' || entry.type === 'delete';

    if (isChange) {
      if (currentHunkLines.length === 0) {
        // Start new hunk, include preceding context
        const contextBefore = diffEntries.slice(Math.max(0, idx - contextSize), idx);
        contextBefore.forEach(c => {
          currentHunkLines.push({ type: 'context', text: c.text, oldLineNum: c.oldIdx, newLineNum: c.newIdx });
          hunkOldCount++;
          hunkNewCount++;
        });
        hunkOldStart = (contextBefore[0]?.oldIdx) || entry.oldIdx || 1;
        hunkNewStart = (contextBefore[0]?.newIdx) || entry.newIdx || 1;
      } else if (pendingContext.length > 0) {
        // Append context between changes
        currentHunkLines.push(...pendingContext);
        pendingContext.forEach(() => {
          hunkOldCount++;
          hunkNewCount++;
        });
        pendingContext = [];
      }

      if (entry.type === 'add') {
        currentHunkLines.push({ type: 'add', text: entry.text, newLineNum: entry.newIdx });
        hunkNewCount++;
      } else {
        currentHunkLines.push({ type: 'delete', text: entry.text, oldLineNum: entry.oldIdx });
        hunkOldCount++;
      }
    } else {
      // Same line (context)
      if (currentHunkLines.length > 0) {
        pendingContext.push({ type: 'context', text: entry.text, oldLineNum: entry.oldIdx, newLineNum: entry.newIdx });
        if (pendingContext.length >= contextSize * 2 || idx === diffEntries.length - 1) {
          // Flush hunk with trailing context
          const trailingContext = pendingContext.slice(0, contextSize);
          currentHunkLines.push(...trailingContext);
          trailingContext.forEach(() => {
            hunkOldCount++;
            hunkNewCount++;
          });

          hunks.push({
            oldStart: hunkOldStart,
            oldLines: hunkOldCount,
            newStart: hunkNewStart,
            newLines: hunkNewCount,
            lines: [...currentHunkLines],
          });

          currentHunkLines = [];
          pendingContext = [];
          hunkOldCount = 0;
          hunkNewCount = 0;
        }
      }
    }
  }

  if (currentHunkLines.length > 0) {
    const trailingContext = pendingContext.slice(0, contextSize);
    currentHunkLines.push(...trailingContext);
    trailingContext.forEach(() => {
      hunkOldCount++;
      hunkNewCount++;
    });

    hunks.push({
      oldStart: hunkOldStart,
      oldLines: hunkOldCount,
      newStart: hunkNewStart,
      newLines: hunkNewCount,
      lines: currentHunkLines,
    });
  }

  // Format into standard unified diff header
  const timestamp = new Date().toISOString();
  let patch = `--- a/app.py\t${timestamp}\n+++ b/app.py\t${timestamp}\n`;

  if (hunks.length === 0) {
    patch += `# No differences found between original and current app.py\n`;
  } else {
    for (const hunk of hunks) {
      patch += `@@ -${hunk.oldStart},${hunk.oldLines} +${hunk.newStart},${hunk.newLines} @@\n`;
      for (const line of hunk.lines) {
        if (line.type === 'add') {
          patch += `+${line.text}\n`;
        } else if (line.type === 'delete') {
          patch += `-${line.text}\n`;
        } else {
          patch += ` ${line.text}\n`;
        }
      }
    }
  }

  return {
    unifiedDiff: patch,
    additions,
    deletions,
    hunks,
  };
}
