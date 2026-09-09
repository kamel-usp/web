<script lang="ts">
  import { SplitPane } from '@rich_harris/svelte-split-pane';
  import CodeMirror from 'svelte-codemirror-editor';
  import { oneDark } from '@codemirror/theme-one-dark';

  import { pasp } from '$lib/lang/pasp';
  import Toolbar from '$lib/ui/Toolbar.svelte';
  import OutputPanel from '$lib/ui/OutputPanel.svelte';
  import FileBrowser from '$lib/ui/FileBrowser.svelte';
  import { currentFile, currentFileContent, currentFileTruncation } from '$lib/stores/editor';
  import { formatBytes, formatCount } from '$lib/limits';

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
              {#if $currentFileTruncation}
                <!-- The buffer below is only the head of the file, so say so
                     before the user reads it as the whole thing. -->
                <p class="truncated" id="truncation-warning" role="status">
                  <strong>
                    Showing the first {formatCount($currentFileTruncation.shownLines)} of
                    {formatCount($currentFileTruncation.totalLines)} lines.
                  </strong>
                  <code>{$currentFile}</code> is {formatBytes($currentFileTruncation.bytes)}, too long
                  to edit here, so it is open read-only and cannot be run. The whole file is still on
                  the server: a program that reads it — with <code>#learn</code> or from a
                  <code>#python</code> block — sees every line.
                </p>
              {/if}
              <!-- `on:change` is wrapped in an arrow function on purpose:
                   `bind:this` is still undefined when handlers are attached,
                   so passing `fileBrowserComp?.saveFile` directly attached
                   nothing and the buffer was never auto-saved. -->
              <CodeMirror
                bind:value={$currentFileContent}
                lang={pasp()}
                theme={oneDark}
                readonly={$currentFileTruncation !== null}
                on:change={() => fileBrowserComp?.saveFile()}
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

  /* `flex`, not `height: 100%`: the truncation banner shares this column, and
     a full-height editor beside it would be clipped by the pane's overflow. */
  #code :global(.codemirror-wrapper) {
    flex: 1 1 0;
    min-height: 0;
    overflow: auto;
  }

  .truncated {
    flex: 0 0 auto;
    margin: 0;
    padding: 8px 12px;
    border-bottom: 1px solid #3a3a3a;
    border-left: 3px solid #d19a66;
    background-color: #241f1a;
    color: #d8c3a5;
    font-size: 12.5px;
    line-height: 1.5;
  }

  .truncated strong {
    color: #f0d9b5;
  }

  .truncated code {
    color: #f0d9b5;
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
