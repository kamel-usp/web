<script>
  import { Modal, Dropzone, Button, Listgroup, ButtonGroup } from "flowbite-svelte";
  import { userID } from "$lib/stores/auth";
  import { get } from "svelte/store";
  import { currentFile, editorTerminal } from "$lib/stores/editor";
  import { FileSolid, AdjustmentsVerticalOutline, UploadSolid } from 'flowbite-svelte-icons';

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
    if (files.length > 0) {
      // TODO: allow multiple files at once by iterating them
      value.push(files[0].name);
      fileList.push(files[0]);
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

  async function uploadFile() {
    const filename = value[0];
    const content = await fileList[0].text();
    const response = await fetch("/api/instance/blob/upload", {
      method: "POST",
      body: JSON.stringify({ filename, content }),
      headers: {
        "content-type": "application/json",
      },
    });
    console.log(response.status);
    let res = await response.json();
    console.log(res);
  }

  async function listFiles() {
    const response = await fetch("/api/instance/blob/list", {
      method: "POST",
      body: JSON.stringify({ }),
      headers: {
        "content-type": "application/json",
      },
    });
    console.log (response.status);
    let res = await response.json ();
    editorTerminal.set ("> " + (res.files == undefined ? "An error ocurred while listing files." : res.files));
    console.log (res);
  }

  function setCurrentFile(name) {
      currentFile.set(name);
  }

  let value = [];
  let fileList = [];
  let clickOutsideModal = false;
  
  let icons = [
      { name: 'HelloWorld.dPasp', icon: FileSolid },
      { name: 'HelloWorld.py', icon: FileSolid },
    ];
</script>

<ButtonGroup>
  <Button>
    <AdjustmentsVerticalOutline class="w-3 h-3 mr-2" />
  </Button>
  <Button on:click={() => (clickOutsideModal = true)}>
    <UploadSolid class="w-3 h-3 mr-2" />
  </Button>
</ButtonGroup>


<Listgroup active items={icons} let:item class="w-100 rounded-none border-0 border-hidden">
    <svelte:component this={item.icon} class="w-3 h-3 mr-2.5" on:click={() => setCurrentFile(item.name)}/>
    <span on:click={() => setCurrentFile(item.name)}>{item.name}</span>
</Listgroup>
<!-- <Button on:click={() => (clickOutsideModal = true)}>File Browser</Button>
<Button on:click={() => (listFiles ())}>List Files</Button> -->

<Modal title="File upload" bind:open={clickOutsideModal} autoclose outsideclose>
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
    <Button color="alternative" on:click={uploadFile}>Submit</Button>
  </svelte:fragment>
</Modal>
