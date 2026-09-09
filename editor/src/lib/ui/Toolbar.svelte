<script lang="ts">
  import { Toolbar, ToolbarButton, Button, Dropdown, Radio, Spinner } from 'flowbite-svelte';
  import { PlayOutline, ChevronDownSolid } from 'flowbite-svelte-icons';
  import { currentFile, currentFileContent, runResult, running } from '$lib/stores/editor';
  import type { RunResult } from '$lib/types';

  interface OptionGroup {
    label: string;
    values: string[];
    /** Index of the selected value. */
    index: number;
  }

  // Kept in sync with SEMANTICS/PSEMANTICS in backend/dPaspRunner/main.py.
  let groups: OptionGroup[] = [
    { label: 'Semantics', values: ['stable', 'partial', 'lstable', 'smproblog'], index: 0 },
    { label: 'PSemantics', values: ['credal', 'maxent'], index: 0 }
  ];

  $: sem = groups[0].values[groups[0].index];
  $: psem = groups[1].values[groups[1].index];

  function select(group: OptionGroup, index: number) {
    group.index = index;
    groups = groups;
  }

  /** Persists the buffer so a run always executes what is on screen. */
  async function saveCurrentFile() {
    const filename = $currentFile;
    if (!filename) return;
    await fetch('/api/instance/blob/upload', {
      method: 'POST',
      body: JSON.stringify({ filename, content: $currentFileContent ?? '' }),
      headers: { 'content-type': 'application/json' }
    });
  }

  async function submit() {
    if ($running) return;
    running.set(true);
    try {
      await saveCurrentFile();

      const code = ($currentFileContent ?? '') + '\n';

      const response = await fetch('/api/instance/run', {
        method: 'POST',
        body: JSON.stringify({ sem, psem, code }),
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
            sem,
            psem,
            response.ok
              ? 'The runner returned a response that was not valid JSON.'
              : `The runner replied ${response.status}.`
          )
        );
      }
    } catch (e) {
      runResult.set(transportError(sem, psem, String(e)));
    } finally {
      running.set(false);
    }
  }

  function transportError(sem: string, psem: string, message: string): RunResult {
    return {
      ok: false,
      sem,
      psem,
      interval: psem === 'credal',
      learned: false,
      elapsed_ms: 0,
      queries: [],
      output: '',
      error: {
        kind: 'internal',
        type: 'TransportError',
        message: `${message}\n\nThe dPASP runner may still be starting up. Try again in a moment.`
      }
    };
  }
</script>

<Toolbar>
  <div class="flex-container">
    {#each groups as group}
      <Button class="dark:bg-gray-900 text-primary-500 dark:hover:bg-gray-700">
        {group.label}: {group.values[group.index]}
        <ChevronDownSolid class="w-3 h-3 ml-2 text-white dark:text-white" />
      </Button>
      <Dropdown class="w-44 p-3 space-y-3 text-sm">
        {#each group.values as value, index}
          <li>
            <Radio
              name={group.label}
              checked={group.index === index}
              on:click={() => select(group, index)}>{value}</Radio
            >
          </li>
        {/each}
      </Dropdown>
    {/each}
  </div>
  <ToolbarButton
    name="run"
    slot="end"
    color="green"
    disabled={$running}
    on:click={submit}
    title="Run the program"
  >
    {#if $running}
      <Spinner class="w-5 h-5" size={6} />
    {:else}
      <PlayOutline class="w-5 h-5" />
    {/if}
  </ToolbarButton>
</Toolbar>

<style>
  .flex-container {
    display: flex;
    gap: 20px;
  }
</style>
