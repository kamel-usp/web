<script lang="ts">
  /**
   * File browser for the workspace inside the caller's runner container:
   * lists files, opens one in the editor, creates a new one, and uploads
   * CSV data files or programs from the local machine.
   */
  import { Modal, Dropzone, Button, ButtonGroup } from "flowbite-svelte";
  import {
    currentFile,
    currentFileContent,
    currentFileTruncation,
    editorNotice,
    ref
  } from "$lib/stores/editor";
  import { FileSolid, AdjustmentsVerticalOutline, UploadSolid } from 'flowbite-svelte-icons';
  import { get } from "svelte/store";
  import { EXAMPLES, findExample } from "$lib/examples";
  import { MAX_EDITOR_LINES, countLines, formatCount } from "$lib/limits";

  /** The one notice this component owns, so it can clear it again. */
  const UNREACHABLE = "Could not reach the dPASP runner. It may still be starting up.";

  /** Files picked in the upload dialog but not yet sent. */
  let pending: File[] = [];
  let refresh = 0;
  let showUploadModal = false;
  let showAddFileModal = false;
  let newFileName = "";

  /** Chosen starting point in the New file dialog; "" is an empty file. */
  let exampleId = "";
  /** Names currently in the workspace, for the collision check below. */
  let existingNames: string[] = [];

  $: selectedExample = exampleId ? findExample(exampleId) : undefined;

  /**
   * Selecting an example fills in its filename, unless the user has already
   * typed one of their own — their text is never overwritten.
   *
   * The id is read from the event rather than from `selectedExample`, which
   * is a reactive derivation: Svelte recomputes it after this handler runs,
   * so reading it here would use the previously selected example.
   */
  function onExampleChange(event: Event) {
    const id = (event.target as HTMLSelectElement).value;
    const suggested = findExample(id)?.filename ?? "";
    const wasSuggested = EXAMPLES.some((e) => e.filename === newFileName.trim());
    if (newFileName.trim() === "" || wasSuggested) newFileName = suggested;
  }

  $: trimmedName = newFileName.trim();
  $: nameCollides = trimmedName !== "" && existingNames.includes(trimmedName);
  $: canCreate = trimmedName !== "" && !nameCollides;

  function addPending(files: File[]) {
    pending = [...pending, ...files];
  }

  const dropHandle = (event: DragEvent) => {
    event.preventDefault();
    const transfer = event.dataTransfer;
    if (!transfer) return;

    // Previously this collected only the file *names* and discarded the File
    // objects, so a drag-and-drop upload sent an empty body. Keep the files.
    if (transfer.items && transfer.items.length > 0) {
      const dropped = [...transfer.items]
        .filter((item) => item.kind === 'file')
        .map((item) => item.getAsFile())
        .filter((file): file is File => file !== null);
      addPending(dropped);
    } else if (transfer.files) {
      addPending([...transfer.files]);
    }
  };

  const handleChange = (event: Event) => {
    const input = event.target as HTMLInputElement;
    if (input.files) addPending([...input.files]);
  };

  /** Short summary of the pending selection, for the dialog. */
  const showFiles = (files: File[]): string => {
    const names = files.map((file) => file.name);
    if (names.length === 1) return names[0];
    const joined = names.join(', ');
    return joined.length > 40 ? joined.slice(0, 40) + '...' : joined;
  };

  async function uploadFile(filename: string, content: string): Promise<void> {
    await fetch("/api/instance/blob/upload", {
      method: "POST",
      body: JSON.stringify({ filename, content }),
      headers: { "content-type": "application/json" },
    });
  }

  async function submitUploadFile() {
    const failed: string[] = [];
    const long: string[] = [];
    for (const file of pending) {
      try {
        const text = await file.text();
        await uploadFile(file.name, text);
        // The text is already here, so counting is free; say up front that
        // this file will open as a prefix, rather than letting the banner be
        // the first the user hears of it.
        const lines = countLines(text);
        if (lines > MAX_EDITOR_LINES) long.push(`${file.name} (${formatCount(lines)} lines)`);
      } catch (e) {
        failed.push(file.name);
      }
    }
    pending = [];

    const notices: string[] = [];
    if (failed.length) notices.push(`Could not upload: ${failed.join(', ')}`);
    if (long.length) {
      notices.push(
        `Uploaded ${long.join(', ')}. The editor shows the first ` +
          `${formatCount(MAX_EDITOR_LINES)} lines of a file this long; programs still read all of it.`
      );
    }
    editorNotice.set(notices.join(' '));

    ref.update((n) => n + 1);
    refresh = get(ref);
  }

  async function listFiles() {
    const response = await fetch("/api/instance/blob/list", {
      method: "POST",
      body: JSON.stringify({}),
      headers: { "content-type": "application/json" },
    });
    const res = await response.json();
    editorNotice.set(
      res.files == undefined ? "Could not list files." : "Files: " + res.files.join(", ")
    );
  }

  interface FileEntry {
    name: string;
    icon: typeof FileSolid;
  }

  async function fetchFiles(): Promise<FileEntry[]> {
    const response = await fetch("/api/instance/blob/list", {
      method: "POST",
      body: JSON.stringify({}),
      headers: { "content-type": "application/json" },
    });
    const res = await response.json();

    if (res.files == undefined) {
      // The runner container may still be starting; report it instead of
      // throwing while rendering the list.
      editorNotice.set(UNREACHABLE);
      return [];
    }

    // Clear only this function's own message. The list is refreshed right
    // after an upload, and clearing unconditionally wiped the notice that
    // upload had just written.
    if (get(editorNotice) === UNREACHABLE) editorNotice.set("");
    existingNames = res.files as string[];
    return res.files.map((name: string) => ({ name, icon: FileSolid }));
  }

  /**
   * Persists the open buffer. Bound by the page to the editor's change event,
   * so edits survive switching files.
   */
  export async function saveFile() {
    if ($currentFile === "") return;
    // Never write back a truncated buffer. It holds only the first
    // MAX_EDITOR_LINES lines of the file, so saving it would delete
    // everything past the cut — silently, and for a data file, entirely.
    // CodeMirror is read-only in that state, but its change event is
    // debounced, so one can still arrive just after a switch to a long file.
    if ($currentFileTruncation) return;
    await uploadFile($currentFile, $currentFileContent ?? "");
  }

  async function setCurrentFile(name: string) {
    await saveFile();
    currentFile.set(name);
    // Cleared before the fetch so that a stale banner never describes the
    // file now being opened.
    currentFileTruncation.set(null);

    const response = await fetch("/api/instance/blob/fetch", {
      method: "POST",
      // Ask for a bounded prefix: an uploaded data file can be far larger
      // than anything worth sending to a text editor.
      body: JSON.stringify({ filename: name, max_lines: MAX_EDITOR_LINES }),
      headers: { "content-type": "application/json" },
    });
    const res = await response.json();
    currentFileContent.set(res.content ?? "");

    if (res.truncated) {
      currentFileTruncation.set({
        totalLines: res.total_lines ?? 0,
        shownLines: res.shown_lines ?? countLines(res.content ?? ""),
        bytes: res.bytes ?? 0,
      });
    }
  }

  async function addNewFile() {
    const name = newFileName.trim();
    // Guarded here as well as on the button: the dialog closes on click
    // (`autoclose`), so a stale click must not overwrite an existing file.
    if (name === "" || existingNames.includes(name)) return;

    const code = selectedExample?.code ?? "";

    await uploadFile(name, code);
    currentFile.set(name);
    currentFileContent.set(code);
    // A file created here is never a prefix; clear any banner left by the
    // file that was open before.
    currentFileTruncation.set(null);

    newFileName = "";
    exampleId = "";
    showAddFileModal = false;

    ref.update((n) => n + 1);
    refresh = get(ref);
  }
</script>

<div class="flex flex-col p-2 gap-2">
  <ButtonGroup>
    <Button title="New file" on:click={() => (showAddFileModal = true)}>
      <FileSolid class="w-3 h-3 mr-2" />
    </Button>
    <Button title="List files" on:click={listFiles}>
      <AdjustmentsVerticalOutline class="w-3 h-3 mr-2" />
    </Button>
    <Button title="Upload a data file" on:click={() => (showUploadModal = true)}>
      <UploadSolid class="w-3 h-3 mr-2" />
    </Button>
  </ButtonGroup>

  <!-- Rendered directly rather than through flowbite's Listgroup, whose slot
       types the item as a string and so cannot carry an icon alongside the
       name. -->
  {#key refresh}
    {#await fetchFiles() then entries}
      {#if entries.length === 0}
        <p class="hint">No files yet. Use the first button to create one.</p>
      {:else}
        <ul class="files">
          {#each entries as entry (entry.name)}
            <li>
              <button
                type="button"
                class="entry"
                class:current={entry.name === $currentFile}
                on:click={() => setCurrentFile(entry.name)}
              >
                <svelte:component this={entry.icon} class="w-3 h-3 mr-2.5" />
                <span>{entry.name}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    {/await}
  {/key}

  <Modal title="Upload a file" bind:open={showUploadModal} autoclose outsideclose>
    <Dropzone
      id="dropzone"
      multiple
      accept=".csv,.tsv,.pasp,.plp,.lp,.pl,.txt,.json"
      on:drop={dropHandle}
      on:dragover={(event) => {
        event.preventDefault();
      }}
      on:change={handleChange}>
      <svg aria-hidden="true" class="mb-3 w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
      {#if pending.length === 0}
        <p class="mb-2 text-sm text-gray-500 dark:text-gray-400"><span class="font-semibold">Click to upload</span> or drag and drop</p>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          CSV data files and dPASP programs (.pasp, .plp, .lp)
        </p>
      {:else}
        <p>{showFiles(pending)}</p>
      {/if}
    </Dropzone>
    <svelte:fragment slot="footer">
      <Button color="alternative" disabled={pending.length === 0} on:click={submitUploadFile}>
        Upload {pending.length || ''}
      </Button>
    </svelte:fragment>
  </Modal>

  <Modal title="New file" bind:open={showAddFileModal} autoclose outsideclose>
    <div class="new-file">
      <label class="field">
        <span class="field-label">Start from</span>
        <select bind:value={exampleId} on:change={onExampleChange}>
          <option value="">Empty file</option>
          {#each EXAMPLES as example (example.id)}
            <option value={example.id}>{example.label}</option>
          {/each}
        </select>
      </label>

      {#if selectedExample}
        <p class="description">{selectedExample.description}</p>
        {#if selectedExample.note}
          <p class="note">{selectedExample.note}</p>
        {/if}
      {:else}
        <p class="description">
          A blank program. Name it with a <code>.pasp</code> extension.
        </p>
      {/if}

      <label class="field">
        <span class="field-label">File name</span>
        <input
          type="text"
          bind:value={newFileName}
          placeholder="example.pasp"
          aria-invalid={nameCollides}
        />
      </label>

      {#if nameCollides}
        <!-- Creating over an existing name used to overwrite it silently. -->
        <p class="error">
          <code>{trimmedName}</code> already exists in your workspace. Choose another name, or open
          the existing file from the list.
        </p>
      {/if}
    </div>

    <svelte:fragment slot="footer">
      <Button color="alternative" disabled={!canCreate} on:click={addNewFile}>Create</Button>
    </svelte:fragment>
  </Modal>
</div>

<style>
  .new-file {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .field-label {
    font-size: 12px;
    font-weight: 500;
    color: #9a9a9a;
  }

  .new-file select,
  .new-file input {
    width: 100%;
    padding: 7px 9px;
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    background-color: #1f1f1f;
    color: #e6e6e6;
    font: inherit;
    font-size: 13px;
  }

  .new-file select:focus,
  .new-file input:focus {
    outline: none;
    border-color: #fe795d;
  }

  .new-file input[aria-invalid='true'] {
    border-color: #f14c4c;
  }

  .description {
    margin: 0;
    color: #9a9a9a;
    font-size: 12.5px;
    line-height: 1.45;
  }

  .note {
    margin: 0;
    padding: 7px 9px;
    border-left: 2px solid #d19a66;
    background-color: #241f1a;
    color: #d8c3a5;
    font-size: 12.5px;
    line-height: 1.45;
  }

  .error {
    margin: 0;
    color: #ff8f7a;
    font-size: 12.5px;
  }

  .files {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .hint {
    padding: 4px 2px;
    color: #8a8a8a;
    font-size: 12px;
  }

  .entry {
    display: flex;
    align-items: center;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    padding: 0;
    color: inherit;
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    padding: 5px 8px;
    border-radius: 4px;
  }

  .entry:hover {
    background-color: #2f2f2f;
  }

  .entry.current {
    background-color: #3a3a3a;
    color: #ffffff;
  }
</style>
