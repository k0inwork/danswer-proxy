import JSZip from 'jszip';

export interface RepoFile {
  path: string;
  content: string;
}

/**
 * Creates and triggers a download of a .zip archive containing repository files.
 */
export async function downloadRepoAsZip(
  files: RepoFile[],
  zipFilename: string = 'danswer-orchestrator-repo.zip'
): Promise<void> {
  const zip = new JSZip();

  for (const file of files) {
    // JSZip handles forward slashes in relative paths
    const cleanPath = file.path.startsWith('/') ? file.path.slice(1) : file.path;
    zip.file(cleanPath, file.content);
  }

  const blob = await zip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 },
  });

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = zipFilename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
