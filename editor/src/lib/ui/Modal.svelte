<script lang="ts">
  /**
   * The dialog used by the New file and Upload flows, replacing flowbite's
   * `Modal`.
   *
   * Built on the native `<dialog>` element with `showModal()`, which is the
   * reason this is short: the browser supplies the backdrop, the top layer,
   * the focus trap, Escape-to-close and `inert` for everything behind it.
   * Reimplementing those by hand is where home-made modals usually go wrong.
   *
   * `open` is bindable, so callers keep flowbite's `bind:open` shape and the
   * two call sites did not have to change.
   */
  import type { Snippet } from 'svelte';

  interface Props {
    open: boolean;
    title: string;
    children: Snippet;
    /** Rendered in the footer row, right-aligned. */
    footer?: Snippet;
  }

  let { open = $bindable(), title, children, footer }: Props = $props();

  let dialog = $state<HTMLDialogElement | null>(null);

  // Drive the element from the prop. `showModal()` on an already-open dialog
  // throws, hence the guards.
  $effect(() => {
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  /**
   * A click on the backdrop lands on the dialog element itself — the content
   * is in a child — which is how "click outside to close" is done without a
   * separate overlay element.
   */
  function onBackdropClick(event: MouseEvent) {
    if (event.target === dialog) open = false;
  }
</script>

<dialog
  bind:this={dialog}
  onclose={() => (open = false)}
  onclick={onBackdropClick}
  aria-label={title}
>
  <div class="panel">
    <header>
      <h2>{title}</h2>
      <button type="button" class="close" onclick={() => (open = false)} aria-label="Close">
        ×
      </button>
    </header>

    <div class="body">
      {@render children()}
    </div>

    {#if footer}
      <footer>
        {@render footer()}
      </footer>
    {/if}
  </div>
</dialog>

<style>
  dialog {
    /*
     * `margin: auto` is what centres a modal `<dialog>`, and it is *not*
     * decoration here — the browser's own stylesheet sets it, together with
     * `inset: 0`, and that pair is the whole centring mechanism.
     *
     * Tailwind 4's preflight resets `margin: 0` on `*` (Tailwind 3 reset only
     * a named list of elements, so this is new), which quietly took the
     * `auto` away and pinned every dialog to the top-left corner. Restating
     * it here is the fix, and it has to stay: it looks redundant against the
     * UA stylesheet precisely because something else is overriding that.
     */
    margin: auto;
    padding: 0;
    border: 1px solid #3a3a3a;
    border-radius: 10px;
    background-color: #262626;
    color: #e6e6e6;
    width: min(32rem, calc(100vw - 2rem));
    /* The New file dialog grows with the chosen example's description, so
       bound it and let the body scroll rather than the dialog overflow. */
    max-height: calc(100vh - 2rem);
  }

  dialog::backdrop {
    background-color: rgb(0 0 0 / 0.55);
  }

  .panel {
    display: flex;
    flex-direction: column;
    max-height: inherit;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    border-bottom: 1px solid #3a3a3a;
  }

  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }

  .close {
    border: 0;
    background: none;
    color: #9a9a9a;
    font-size: 20px;
    line-height: 1;
    padding: 0 4px;
    cursor: pointer;
  }

  .close:hover {
    color: #e6e6e6;
  }

  .body {
    padding: 14px;
    overflow-y: auto;
  }

  footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 14px;
    border-top: 1px solid #3a3a3a;
  }
</style>
