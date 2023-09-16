<script>
  import { HomeOutline, EnvelopeOutline } from 'flowbite-svelte-icons';
  import { Textarea, Toolbar, ToolbarGroup, ToolbarButton, Button } from 'flowbite-svelte';
  import { PlayOutline } from 'flowbite-svelte-icons';
  import { editor } from '$lib/stores/editor.ts';
  import { get } from 'svelte/store';  
  import { Spinner } from 'flowbite-svelte';

  let submitting = false;
  
  async function submit() {
    submitting = true;
    const code = get(editor);
      const response = await fetch('/api/containermanager/run', {
        method: 'POST',
        body: JSON.stringify({ code }),
        headers: {
          'content-type': 'application/json'
        }
      });
      console.log(response.status);
      let res = await response.json();
      console.log(res);
      submitting = false;
  }
</script>

<Toolbar>
<!--   <ToolbarGroup>
    <ToolbarButton name="Attach file"><PaperClipOutline class="w-5 h-5 rotate-45" /></ToolbarButton>
    <ToolbarButton name="Embed map"><MapPinAltSolid class="w-5 h-5" /></ToolbarButton>
    <ToolbarButton name="Upload image"><ImageOutline class="w-5 h-5" /></ToolbarButton>
  </ToolbarGroup>
  <ToolbarGroup>
    <ToolbarButton name="Format code"><PlayOutline class="w-5 h-5" /></ToolbarButton>
    <ToolbarButton name="Add emoji"><FaceGrinOutline class="w-5 h-5" /></ToolbarButton>
  </ToolbarGroup> -->
  <ToolbarButton name="send" slot="end" color="green" on:click={submit}>
    {#if submitting == false}
      <PlayOutline class="w-5 h-5" />
    {:else}
      <Spinner class="w-5 h-5" size={6} />
    {/if}
  </ToolbarButton>
</Toolbar>
