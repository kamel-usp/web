<script lang="ts">
  import { SplitPane } from '@rich_harris/svelte-split-pane';
  import CodeMirror from 'svelte-codemirror-editor';
  import { oneDark } from '@codemirror/theme-one-dark';

  import { pasp } from '$lib/lang/pasp';
  import Toolbar from '$lib/ui/Toolbar.svelte';
  import OutputPanel from '$lib/ui/OutputPanel.svelte';
  import FileBrowser from '$lib/ui/FileBrowser.svelte';
  import { currentFile, currentFileContent } from '$lib/stores/editor';

  let fileBrowserComp: FileBrowser;
</script>

<div class="page-container">
  <Toolbar />

  <div class="workspace">
    <SplitPane type="horizontal" min="120px" max="30%" pos="18%" id="shell">
      <section slot="a" class="pane" id="browser">
        <FileBrowser bind:this={fileBrowserComp} />
      </section>

      <section slot="b" class="pane">
        <SplitPane type="vertical" min="25%" max="85%" pos="62%" id="editor-output">
          <section slot="a" class="pane" id="code">
            {#if $currentFile != ''}
              <CodeMirror
                bind:value={$currentFileContent}
                lang={pasp()}
                theme={oneDark}
                on:change={fileBrowserComp?.saveFile}
                styles={{
                  '&': { height: '100%', fontSize: '13px' },
                  '.cm-scroller': { overflow: 'auto' }
                }}
              />
            {:else}
              <p class="no-file">
                Create or open a <code>.pasp</code> file to start writing a program.
              </p>
            {/if}
          </section>

          <section slot="b" class="pane">
            <OutputPanel />
          </section>
        </SplitPane>
      </section>
    </SplitPane>
  </div>
</div>

<style>
  .page-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    /* Leaves room for the fixed navbar. */
    padding-top: 48px;
    box-sizing: border-box;
  }

  .workspace {
    flex: 1 1 auto;
    min-height: 0;
  }

  .pane {
    height: 100%;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  #browser {
    overflow: auto;
  }

  #code {
    background-color: #282c34;
  }

  #code :global(.codemirror-wrapper) {
    height: 100%;
    min-height: 0;
    overflow: auto;
  }

  .no-file {
    margin: 16px;
    color: #8a8a8a;
    font-size: 13px;
  }

  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
</style>
