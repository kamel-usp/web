/**
 * Saving the open program to the user's machine.
 *
 * Split from the toolbar so the part that has to be right can be tested: a
 * file that is open as a *prefix* (see `MAX_EDITOR_LINES`) must be downloaded
 * whole, not as the 1000 lines on screen. Handing someone a silently
 * truncated copy of their own data file would be worse than refusing.
 */

export interface DownloadPlan {
  /** Name to save under. */
  filename: string;
  /**
   * True when the buffer on screen is only part of the file, so the content
   * has to be fetched from the runner before saving.
   */
  needsFullFile: boolean;
}

/** What to save, or `null` when there is nothing open to save. */
export function planDownload(currentFile: string, truncated: boolean): DownloadPlan | null {
  const filename = currentFile.trim();
  if (filename === '') return null;
  return { filename, needsFullFile: truncated };
}

/**
 * Hand `text` to the browser as a file download.
 *
 * An object URL rather than a `data:` URL: a program can be megabytes, and
 * data URLs are length-limited in some browsers. Revoked on the next tick,
 * once the click has been dispatched.
 */
export function saveTextAsFile(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
