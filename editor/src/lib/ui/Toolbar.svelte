<script lang="ts">
  import { Toolbar, ToolbarButton, Spinner } from 'flowbite-svelte';
  import { PlayOutline, DownloadSolid } from 'flowbite-svelte-icons';
  import {
    currentFile,
    currentFileContent,
    currentFileTruncation,
    runResult,
    running
  } from '$lib/stores/editor';
  import { formatCount } from '$lib/limits';
  import { planDownload, saveTextAsFile } from '$lib/download';
  import type { RunResult } from '$lib/types';

  /**
   * There are no semantics controls here any more.
   *
   * dPASP reads `#semantics` from the program itself — its parser pre-scans
   * the source and lets the directive override whatever the caller asked for
   * — so the dropdowns that used to sit here were a second, weaker source of
   * truth. On a program containing `#semantics maxent.` the toolbar would
   * cheerfully say "credal" while the run used max-entropy. The semantics in
   * force are now reported by the output panel, from the parsed program.
   */

  /** True while the whole file is being fetched for a download. */
  let downloading = false;

  async function download() {
    const plan = planDownload($currentFile, $currentFileTruncation !== null);
    if (!plan || downloading) return;

    if (!plan.needsFullFile) {
      saveTextAsFile(plan.filename, $currentFileContent ?? '');
      return;
    }

    // The editor is showing a prefix. Ask the runner for the whole file
    // rather than saving what is on screen.
    downloading = true;
    try {
      const response = await fetch('/api/instance/blob/fetch', {
        method: 'POST',
        body: JSON.stringify({ filename: plan.filename }),
        headers: { 'content-type': 'application/json' }
      });
      const body = await response.json();
      if (typeof body?.content !== 'string') throw new Error('no content in the reply');
      saveTextAsFile(plan.filename, body.content);
    } catch (e) {
      runResult.set(
        errorResult(
          'DownloadFailed',
          `Could not fetch ${plan.filename} from the runner to download it in full. ` +
            'The editor is only showing part of that file, so saving what is on ' +
            'screen would give you a truncated copy.'
        )
      );
    } finally {
      downloading = false;
    }
  }

  async function saveCurrentFile() {
    const filename = $currentFile;
    if (!filename) return;
    // A truncated buffer is a prefix of the file; writing it back would
    // delete the rest. `submit` refuses to run in that state anyway.
    if ($currentFileTruncation) return;
    await fetch('/api/instance/blob/upload', {
      method: 'POST',
      body: JSON.stringify({ filename, content: $currentFileContent ?? '' }),
      headers: { 'content-type': 'application/json' }
    });
  }

  async function submit() {
    if ($running) return;

    // The run button is disabled in this state; this is the second guard,
    // because running a prefix of a program silently answers the wrong
    // question rather than failing.
    const cut = $currentFileTruncation;
    if (cut) {
      runResult.set(
        errorResult(
          'TruncatedFile',
          `${$currentFile} is open read-only: the editor is showing its first ` +
            `${formatCount(cut.shownLines)} of ${formatCount(cut.totalLines)} lines. ` +
            'Running that prefix would not be running this program.'
        )
      );
      return;
    }

    running.set(true);
    try {
      await saveCurrentFile();

      const code = ($currentFileContent ?? '') + '\n';

      // The program is the whole request: semantics come from its own
      // `#semantics` directive, and the reply reports which were used.
      const response = await fetch('/api/instance/run', {
        method: 'POST',
        body: JSON.stringify({ code }),
        headers: { 'content-type': 'application/json' }
      });

      // The runner reports faulty programs in the body with `ok: false`, and
      // the proxy reports gateway problems in the same shape, so the body is
      // worth reading even on a non-2xx status.
      let payload: RunResult | null = null;
      try {
        payload = await response.json();
      } catch (e) {
        payload = null;
      }

      if (payload && typeof payload === 'object' && 'queries' in payload) {
        runResult.set(payload);
      } else {
        runResult.set(
          transportError(
            response.ok
              ? 'The runner returned a response that was not valid JSON.'
              : `The runner replied ${response.status}.`
          )
        );
      }
    } catch (e) {
      runResult.set(transportError(String(e)));
    } finally {
      running.set(false);
    }
  }

  /** A failed-run body, so one renderer handles every way a run can fail. */
  function errorResult(type: string, message: string): RunResult {
    return {
      ok: false,
      // Nothing was parsed, so these are dPASP's defaults rather than a
      // report of anything.
      sem: 'stable',
      psem: 'credal',
      interval: true,
      learned: false,
      elapsed_ms: 0,
      queries: [],
      output: '',
      error: { kind: 'internal', type, message }
    };
  }

  function transportError(message: string): RunResult {
    return errorResult(
      'TransportError',
      `${message}\n\nThe dPASP runner may still be starting up. Try again in a moment.`
    );
  }
</script>

<Toolbar>
  <div class="flex-container">
    {#if $currentFile}
      <span class="filename" title="The open file">{$currentFile}</span>
      {#if $currentFileTruncation}
        <span class="badge">partial view</span>
      {/if}
    {:else}
      <span class="filename empty">no file open</span>
    {/if}
  </div>

  <!-- One element, not two: flowbite's Toolbar is `justify-between`, and each
       child of the end slot becomes a flex child of it — two buttons would be
       pushed apart, one landing in the middle of the bar. -->
  <div class="actions" slot="end">
    <ToolbarButton
      name="download"
      color="default"
      disabled={!$currentFile || downloading}
      class={!$currentFile || downloading ? 'opacity-40 cursor-not-allowed' : ''}
      on:click={download}
      title={$currentFileTruncation
        ? 'Download the whole file — more than the editor is showing'
        : 'Download this program'}
    >
      {#if downloading}
        <Spinner class="w-5 h-5" size={6} />
      {:else}
        <DownloadSolid class="w-5 h-5" />
      {/if}
    </ToolbarButton>

    <!-- flowbite gives a disabled ToolbarButton no styling of its own, so the
         class below is what stops an unusable play button from looking ready. -->
    <ToolbarButton
      name="run"
      color="green"
      disabled={$running || $currentFileTruncation !== null}
      class={$currentFileTruncation ? 'opacity-40 cursor-not-allowed' : ''}
      on:click={submit}
      title={$currentFileTruncation
        ? 'This file is too long to open whole, so only part of it is on screen. Running that part would not be running the program.'
        : 'Run the program'}
    >
      {#if $running}
        <Spinner class="w-5 h-5" size={6} />
      {:else}
        <PlayOutline class="w-5 h-5" />
      {/if}
    </ToolbarButton>
  </div>
</Toolbar>

<style>
  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .flex-container {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .filename {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    color: #d6d6d6;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .filename.empty {
    color: #7a7a7a;
    font-style: italic;
  }

  .badge {
    padding: 1px 7px;
    border: 1px solid #d19a66;
    border-radius: 999px;
    color: #d19a66;
    font-size: 11px;
    white-space: nowrap;
  }
</style>
