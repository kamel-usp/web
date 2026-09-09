<script lang="ts">
  /**
   * Output panel for a dPASP run.
   *
   * Replaces the previous behaviour, where results were written back into the
   * user's source as `% RESULT:` comments and only errors reached a console.
   * Query probabilities now have their own table, the program's own output and
   * any solver error each have a tab, and the source is never rewritten.
   */
  import { runResult, running, editorNotice } from '$lib/stores/editor';
  import { formatBound, boundFraction } from '$lib/types';
  import type { RunResult } from '$lib/types';

  type Tab = 'probabilities' | 'output' | 'error';
  let active: Tab = 'probabilities';

  /** Tracks which result the tab was auto-selected for, so a manual choice sticks. */
  let autoSelectedFor: RunResult | null = null;

  $: if ($runResult && $runResult !== autoSelectedFor) {
    autoSelectedFor = $runResult;
    active = $runResult.error
      ? 'error'
      : $runResult.queries.length === 0 && $runResult.output
        ? 'output'
        : 'probabilities';
  }

  $: result = $runResult;
  $: queryCount = result ? result.queries.length : 0;
  $: hasOutput = !!(result && result.output);
  $: hasError = !!(result && result.error);

  const ERROR_LABELS: Record<string, string> = {
    parse: 'Syntax error',
    runtime: 'Solver error',
    timeout: 'Timed out',
    internal: 'Runner error'
  };
</script>

<section id="output-panel">
  <header>
    <nav>
      <button class:active={active === 'probabilities'} on:click={() => (active = 'probabilities')}>
        Probabilities{#if queryCount}<span class="badge">{queryCount}</span>{/if}
      </button>
      <button class:active={active === 'output'} on:click={() => (active = 'output')}>
        Output{#if hasOutput}<span class="dot" />{/if}
      </button>
      <button
        class:active={active === 'error'}
        class:has-error={hasError}
        on:click={() => (active = 'error')}
      >
        Errors{#if hasError}<span class="dot error" />{/if}
      </button>
    </nav>

    <div class="status">
      {#if $running}
        <span class="pill running">running…</span>
      {:else if result}
        <span class="pill">{result.sem}</span>
        <span class="pill">{result.psem}</span>
        {#if result.learned}<span class="pill accent">learned</span>{/if}
        <span class="elapsed">{result.elapsed_ms} ms</span>
      {/if}
    </div>
  </header>

  <div class="body">
    {#if $editorNotice}
      <p class="notice">{$editorNotice}</p>
    {/if}

    {#if active === 'probabilities'}
      {#if !result}
        <p class="empty">Press the play button to run the program.</p>
      {:else if result.error}
        <p class="empty">
          The program did not run. See the <button class="link" on:click={() => (active = 'error')}
            >Errors</button
          > tab.
        </p>
      {:else if queryCount === 0}
        <p class="empty">
          The program ran, but has no <code>#query</code> directives, so there are no probabilities
          to show.
        </p>
      {:else}
        <table>
          <thead>
            <tr>
              <th class="q">Query</th>
              {#if result.interval}
                <th class="num">Lower</th>
                <th class="num">Upper</th>
              {:else}
                <th class="num">Probability</th>
              {/if}
              <th class="bar-col" />
            </tr>
          </thead>
          <tbody>
            {#each result.queries as q}
              <tr>
                <td class="q"><code>{q.query}</code></td>
                {#if result.interval}
                  <td class="num">{formatBound(q.lower)}</td>
                  <td class="num">{formatBound(q.upper)}</td>
                {:else}
                  <td class="num">{formatBound(q.values[0])}</td>
                {/if}
                <td class="bar-col">
                  <!-- The track spans [0, 1]; the fill spans the credal
                       interval, degenerating to a thin marker for a point
                       value. -->
                  <div class="track" title="0 to 1">
                    <div
                      class="fill"
                      style="left: {boundFraction(q.lower) * 100}%; width: {Math.max(
                        1,
                        (boundFraction(q.upper) - boundFraction(q.lower)) * 100
                      )}%"
                    />
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {:else if active === 'output'}
      {#if hasOutput && result}
        <pre class="stream">{result.output}</pre>
      {:else}
        <p class="empty">The program printed nothing.</p>
      {/if}
    {:else if hasError && result?.error}
      <div class="error-box">
        <p class="error-head">
          <span class="kind">{ERROR_LABELS[result.error.kind] ?? result.error.kind}</span>
          <span class="type">{result.error.type}</span>
          {#if result.error.line !== undefined}
            <span class="where">
              line {result.error.line}{#if result.error.column !== undefined}, column {result.error
                  .column}{/if}
            </span>
          {/if}
        </p>
        <pre class="stream">{result.error.message}</pre>
      </div>
    {:else}
      <p class="empty">No errors.</p>
    {/if}
  </div>
</section>

<style>
  #output-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    background-color: #1a1a1a;
    color: #e6e6e6;
    border-top: 1px solid #333;
    font-size: 13px;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 0 10px;
    border-bottom: 1px solid #2f2f2f;
    background-color: #202020;
    flex: 0 0 auto;
  }

  nav {
    display: flex;
    gap: 2px;
  }

  nav button {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    border: 0;
    border-bottom: 2px solid transparent;
    background: none;
    color: #9a9a9a;
    font: inherit;
    cursor: pointer;
  }

  nav button:hover {
    color: #d8d8d8;
  }

  nav button.active {
    color: #ffffff;
    border-bottom-color: #fe795d;
  }

  nav button.has-error {
    color: #ff8f7a;
  }

  .badge {
    padding: 0 6px;
    border-radius: 9px;
    background-color: #3a3a3a;
    color: #d8d8d8;
    font-size: 11px;
    line-height: 16px;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: #6a9955;
  }

  .dot.error {
    background-color: #f14c4c;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #8a8a8a;
    font-size: 11px;
  }

  .pill {
    padding: 2px 7px;
    border: 1px solid #3a3a3a;
    border-radius: 10px;
    color: #b9b9b9;
  }

  .pill.accent {
    border-color: #fe795d;
    color: #fe795d;
  }

  .pill.running {
    border-color: #fe795d;
    color: #fe795d;
  }

  .elapsed {
    font-variant-numeric: tabular-nums;
  }

  .body {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    padding: 8px 10px 14px;
  }

  .empty {
    margin: 10px 2px;
    color: #8a8a8a;
  }

  .notice {
    margin: 0 0 8px;
    padding: 6px 8px;
    border-left: 2px solid #fe795d;
    background-color: #241f1d;
    color: #d8c8c2;
  }

  .link {
    border: 0;
    background: none;
    padding: 0;
    color: #fe795d;
    font: inherit;
    text-decoration: underline;
    cursor: pointer;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 5px 8px;
    text-align: left;
    border-bottom: 1px solid #262626;
    vertical-align: middle;
  }

  th {
    position: sticky;
    top: -8px;
    background-color: #1a1a1a;
    color: #8a8a8a;
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  td.q code {
    color: #e6e6e6;
    font-size: 12.5px;
    white-space: nowrap;
  }

  th.num,
  td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  td.num {
    color: #d19a66;
  }

  th.bar-col,
  td.bar-col {
    width: 34%;
    min-width: 90px;
  }

  .track {
    position: relative;
    height: 6px;
    border-radius: 3px;
    background-color: #2b2b2b;
  }

  .fill {
    position: absolute;
    top: 0;
    height: 100%;
    min-width: 2px;
    border-radius: 3px;
    background-color: #fe795d;
  }

  .stream {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    color: #cfcfcf;
    font-size: 12.5px;
    line-height: 1.45;
  }

  .error-box {
    border-left: 2px solid #f14c4c;
    padding: 2px 0 2px 10px;
  }

  .error-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px;
    margin: 0 0 6px;
  }

  .kind {
    color: #ff8f7a;
    font-weight: 600;
  }

  .type,
  .where {
    color: #8a8a8a;
    font-size: 11.5px;
  }

  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
</style>
