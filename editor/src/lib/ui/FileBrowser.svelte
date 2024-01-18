<script>
  import { Modal, Dropzone, Button, Listgroup, ButtonGroup } from "flowbite-svelte";
  import { currentFile, currentFileContent, editorTerminal, ref } from "$lib/stores/editor";
  import { FileSolid, AdjustmentsVerticalOutline, UploadSolid } from 'flowbite-svelte-icons';
  import { get } from "svelte/store";

  const dropHandle = (event) => {
    value = [];
    event.preventDefault();
    if (event.dataTransfer.items) {
      [...event.dataTransfer.items].forEach((item, i) => {
        if (item.kind === 'file') {
          const file = item.getAsFile();
          value.push(file.name);
          value = value;
        }
      });
    } else {
      [...event.dataTransfer.files].forEach((file, i) => {
        value = file.name;
      });
    }
  };

  const handleChange = (event) => {
    const files = event.target.files;
    for (let i = 0; i < files.length; i++) {
      value.push(files[i].name);
      fileList.push(files[i]);
      value = value;
    }
  };

  const showFiles = (files) => {
    if (files.length === 1) return files[0];
    let concat = '';
    files.map((file) => {
      concat += file;
      concat += ',';
      concat += ' ';
    });

    if (concat.length > 40) concat = concat.slice(0, 40);
    concat += '...';
    return concat;
  };

  async function uploadFile(filename, content) {
    const response = await fetch("/api/instance/blob/upload", {
      method: "POST",
      body: JSON.stringify({ filename, content }),
      headers: {
        "content-type": "application/json",
      },
    });
    let res = await response.json();
  }

  async function submitUploadFile() {
    while (fileList.length > 0) {
      const content = await fileList[0].text();
      const filename = value[0];
  
      fileList.shift();
      value.shift();
      await uploadFile(filename, content);
    }
    ref.update((n) => n + 1);
    refresh = get(ref);
  }

  async function listFiles() {
    const response = await fetch("/api/instance/blob/list", {
      method: "POST",
      body: JSON.stringify({ }),
      headers: {
        "content-type": "application/json",
      },
    });
    let res = await response.json ();
    editorTerminal.set ("> " + (res.files == undefined ? "An error ocurred while listing files." : res.files));
  }

  async function fetchFiles() {
    const response = await fetch("/api/instance/blob/list", {
      method: "POST",
      body: JSON.stringify({ }),
      headers: {
        "content-type": "application/json",
      },
    });
    let res = await response.json ();
    editorTerminal.set ("> " + (res.files == undefined ? "An error ocurred while listing files." : ""));
    const data = [];
    for (const filename of res.files) {
      data.push({name: filename, icon: FileSolid});
    }
    return data;
  }

  async function setCurrentFile(name) {
      await uploadFile($currentFile, $currentFileContent);
      currentFile.set(name);
      const response = await fetch("/api/instance/blob/fetch", {
        method: "POST",
        body: JSON.stringify({filename: name}),
        headers: {
          "content-type": "application/json",
        },
      });
      let res = await response.json();
      currentFileContent.set(res.content)
  }

  async function addNewFile() {
    await uploadFile(inputValue, "");
    currentFile.set(inputValue);
    currentFileContent.set("");

    inputValue = ""
    clickOutsideModalAddFile = false;

    ref.update((n) => n + 1);
    refresh = get(ref);
  }

  let refresh = 0;
  let value = [];
  let fileList = [];
  let clickOutsideModalUpload = false;
  let clickOutsideModalAddFile = false;
  let inputValue = "";
</script>

<div class="flex flex-col p-2 gap-2">
  <ButtonGroup>
    <Button on:click={() => (clickOutsideModalAddFile = true)}>
      <FileSolid class="w-3 h-3 mr-2" />
    </Button>
    <Button on:click={listFiles}>
      <AdjustmentsVerticalOutline class="w-3 h-3 mr-2" />
    </Button>
    <Button on:click={() => (clickOutsideModalUpload = true)}>
      <UploadSolid class="w-3 h-3 mr-2" />
    </Button>
  </ButtonGroup>

  {#key refresh}
    {#await fetchFiles() then icons}
      <Listgroup active items={icons} let:item class="w-100 rounded-none border-0 border-hidden">
        {#if item}
          <svelte:component this={item.icon} class="w-3 h-3 mr-2.5" on:click={() => setCurrentFile(item.name)}/>
          <span on:click={() => setCurrentFile(item.name)}>{item.name}</span>
        {/if}
      </Listgroup>
    {/await}
  {/key}

  <Modal title="File upload" bind:open={clickOutsideModalUpload} autoclose outsideclose>
    <Dropzone
      id="dropzone"
      on:drop={dropHandle}
      on:dragover={(event) => {
        event.preventDefault();
      }}
      on:change={handleChange}>
      <svg aria-hidden="true" class="mb-3 w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
      {#if value.length === 0}
        <p class="mb-2 text-sm text-gray-500 dark:text-gray-400"><span class="font-semibold">Click to upload</span> or drag and drop</p>
        <p class="text-xs text-gray-500 dark:text-gray-400">SVG, PNG, JPG or GIF (MAX. 800x400px)</p>
      {:else}
        <p>{showFiles(value)}</p>
      {/if}
    </Dropzone>
    <svelte:fragment slot="footer">
      <Button color="alternative" on:click={submitUploadFile}>Submit</Button>
    </svelte:fragment>
  </Modal>

  <Modal title="Add file" bind:open={clickOutsideModalAddFile} autoclose outsideclose>
    <p class="mb-2 text-sm text-gray-500 dark:text-gray-400">
      <span class="font-semibold">Click to add</span> a new file
    </p>
  
    <input type="text" bind:value={inputValue} placeholder="Enter file name" />
  
    <svelte:fragment slot="footer">
      <Button color="alternative" on:click={addNewFile}>Add file</Button>
    </svelte:fragment>
  </Modal>
</div>

