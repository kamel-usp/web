<script lang="ts">
  /**
   * File browser for the workspace inside the caller's runner container:
   * lists files, opens one in the editor, creates a new one, and uploads
   * CSV data files or programs from the local machine.
   */
  import { Modal, Dropzone, Button, ButtonGroup } from "flowbite-svelte";
  import { currentFile, currentFileContent, editorNotice, ref } from "$lib/stores/editor";
  import { FileSolid, AdjustmentsVerticalOutline, UploadSolid } from 'flowbite-svelte-icons';
  import { get } from "svelte/store";

  /** Files picked in the upload dialog but not yet sent. */
  let pending: File[] = [];
  let refresh = 0;
  let showUploadModal = false;
  let showAddFileModal = false;
  let newFileName = "";

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
    for (const file of pending) {
      try {
        await uploadFile(file.name, await file.text());
      } catch (e) {
        failed.push(file.name);
      }
    }
    pending = [];
    editorNotice.set(failed.length ? `Could not upload: ${failed.join(', ')}` : "");

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
      editorNotice.set("Could not reach the dPASP runner. It may still be starting up.");
      return [];
    }

    editorNotice.set("");
    return res.files.map((name: string) => ({ name, icon: FileSolid }));
  }

  /**
   * Persists the open buffer. Bound by the page to the editor's change event,
   * so edits survive switching files.
   */
  export async function saveFile() {
    if ($currentFile === "") return;
    await uploadFile($currentFile, $currentFileContent ?? "");
  }

  async function setCurrentFile(name: string) {
    if ($currentFile !== "") await uploadFile($currentFile, $currentFileContent ?? "");
    currentFile.set(name);

    const response = await fetch("/api/instance/blob/fetch", {
      method: "POST",
      body: JSON.stringify({ filename: name }),
      headers: { "content-type": "application/json" },
    });
    const res = await response.json();
    currentFileContent.set(res.content ?? "");
  }

  async function addNewFile() {
    const name = newFileName.trim();
    if (name === "") return;

    await uploadFile(name, "");
    currentFile.set(name);
    currentFileContent.set("");

    newFileName = "";
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
    <p class="mb-2 text-sm text-gray-500 dark:text-gray-400">
      Name the file, ending in <code>.pasp</code> for a dPASP program.
    </p>

    <input type="text" bind:value={newFileName} placeholder="example.pasp" />

    <svelte:fragment slot="footer">
      <Button color="alternative" disabled={newFileName.trim() === ''} on:click={addNewFile}>
        Create
      </Button>
    </svelte:fragment>
  </Modal>
</div>

<style>
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
