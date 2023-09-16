<script>
  import { HomeOutline, EnvelopeOutline } from 'flowbite-svelte-icons';
  import { Textarea, Toolbar, ToolbarGroup, ToolbarButton, Button } from 'flowbite-svelte';
  import { PlayOutline } from 'flowbite-svelte-icons';
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
  <ToolbarButton name="send" slot="end" color="green" size="xs"><PlayOutline class="w-5 h-5" /></ToolbarButton>
</Toolbar>
