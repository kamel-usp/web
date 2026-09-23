<script lang="ts">
  /**
   * File browser for the workspace inside the caller's runner container:
   * lists files, opens one in the editor, creates a new one, and uploads
   * CSV data files or programs from the local machine.
   */
  import Modal from "$lib/ui/Modal.svelte";
  import Dropzone from "$lib/ui/Dropzone.svelte";
  import Button from "$lib/ui/Button.svelte";
  import {
    currentFile,
    currentFileContent,
    currentFileTruncation,
    editorNotice,
    ref
  } from "$lib/stores/editor";
  import Icon from "$lib/ui/icons/Icon.svelte";
  import { FILE, UPLOAD, fileGlyph } from "$lib/ui/icons/paths";
  import { get } from "svelte/store";
  import { EXAMPLES, findExample } from "$lib/examples";
  import { MAX_EDITOR_LINES, countLines, formatCount } from "$lib/limits";

  /** The one notice this component owns, so it can clear it again. */
  const UNREACHABLE = "Could not reach the dPASP runner. It may still be starting up.";

  /** Files picked in the upload dialog but not yet sent. */
  let pending: File[] = $state([]);
  let refresh = $state(0);
  let showUploadModal = $state(false);
  let showAddFileModal = $state(false);
  let newFileName = $state("");

  /** Chosen starting point in the New file dialog; "" is an empty file. */
  let exampleId = $state("");
  /** Names currently in the workspace, for the collision check below. */
  let existingNames: string[] = $state([]);

  const selectedExample = $derived(exampleId ? findExample(exampleId) : undefined);

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

  const trimmedName = $derived(newFileName.trim());
  const nameCollides = $derived(trimmedName !== "" && existingNames.includes(trimmedName));
  const canCreate = $derived(trimmedName !== "" && !nameCollides);

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

  interface FileEntry {
    name: string;
    /** Which glyph this file gets, chosen from its extension. */
    glyph: ReturnType<typeof fileGlyph>;
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
    return res.files.map((name: string) => ({ name, glyph: fileGlyph(name) }));
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
    // Guarded here as well as on the button: the dialog closes as this runs,
    // so a stale click must not overwrite an existing file.
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
  <!-- Two actions. There used to be a third, "List files", which printed the
       names into the output panel's notice line — the same names this panel
       is already showing. -->
  <div class="group" role="group" aria-label="Workspace actions">
    <Button title="New file" onclick={() => (showAddFileModal = true)}>
      <Icon d={FILE} solid size={16} />
    </Button>
    <Button title="Upload a data file" onclick={() => (showUploadModal = true)}>
      <Icon d={UPLOAD} solid size={16} />
    </Button>
  </div>

  <!-- Rendered directly rather than through a list component: an entry needs
       an icon beside its name, which flowbite's `Listgroup` could not carry
       because its slot typed the item as a string. -->
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
                onclick={() => setCurrentFile(entry.name)}
              >
                <Icon
                  d={entry.glyph.d}
                  solid={entry.glyph.solid}
                  size={14}
                  title={entry.glyph.label}
                  class="entry-icon"
                />
                <span>{entry.name}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    {/await}
  {/key}

  <Modal title="Upload a file" bind:open={showUploadModal}>
    <Dropzone
      id="dropzone"
      multiple
      accept=".csv,.tsv,.pasp,.plp,.lp,.pl,.txt,.json"
      ondrop={dropHandle}
      onchange={handleChange}
    >
      <Icon d={UPLOAD} solid size={36} class="dropzone-icon" />
      {#if pending.length === 0}
        <p class="dz-primary"><strong>Click to upload</strong> or drag and drop</p>
        <p class="dz-secondary">CSV data files and dPASP programs (.pasp, .plp, .lp)</p>
      {:else}
        <p class="dz-primary">{showFiles(pending)}</p>
      {/if}
    </Dropzone>

    {#snippet footer()}
      <Button variant="alternative" disabled={pending.length === 0} onclick={submitUploadFile}>
        Upload {pending.length || ''}
      </Button>
    {/snippet}
  </Modal>

  <Modal title="New file" bind:open={showAddFileModal}>
    <div class="new-file">
      <label class="field">
        <span class="field-label">Start from</span>
        <select bind:value={exampleId} onchange={onExampleChange}>
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

    {#snippet footer()}
      <Button variant="alternative" disabled={!canCreate} onclick={addNewFile}>Create</Button>
    {/snippet}
  </Modal>
</div>

<style>
  .group {
    display: flex;
  }

  .group :global(button) {
    border-radius: 0;
  }

  .group :global(button:first-child) {
    border-radius: 6px 0 0 6px;
  }

  .group :global(button:last-child) {
    border-radius: 0 6px 6px 0;
  }

  .group :global(button + button) {
    border-left: 1px solid #52525b;
  }

  .dz-primary {
    margin: 8px 0 2px;
    font-size: 13px;
    color: #a1a1aa;
  }

  .dz-secondary {
    margin: 0;
    font-size: 12px;
    color: #8a8a8a;
  }

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

  .entry :global(.entry-icon) {
    margin-right: 10px;
  }

  .entry {
    display: flex;
    align-items: center;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    padding: 0;
    color: #ffffff;
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    padding: 5px 8px;
    border-radius: 4px;
  }

  .entry:hover {
    background-color: #383838;
  }

  /*
   * The open file is named in the accent — the same `--color-primary-500` the
   * title bar uses for "dPASP Playground", so the one pink thing on screen is
   * always "where you are". The icon follows, since `Icon.svelte` draws in
   * `currentColor`.
   *
   * The row is *recessed* rather than lightened, which is the less obvious
   * half. Selection used to be a lighter #3a3a3a, and the accent on that
   * measures 4.39:1 — under the 4.5:1 AA floor for 13 px text. Darkening the
   * row instead of lightening it takes the same colour to 5.84:1, so the
   * selected file is the most readable line in the list rather than the least.
   */
  .entry.current {
    background-color: #262626;
    color: var(--color-primary-500);
  }
</style>
