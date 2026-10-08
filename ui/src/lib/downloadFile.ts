/** Thin browser download adapter over Blob + temporary anchor. */

export type DownloadArtifact = {
  filename: string;
  mimeType: string;
  content: string;
};

export function downloadArtifact(artifact: DownloadArtifact): void {
  const blob = new Blob([artifact.content], { type: artifact.mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = artifact.filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
