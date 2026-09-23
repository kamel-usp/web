<script lang="ts">
  /**
   * The drop target in the Upload dialog, replacing flowbite's `Dropzone`.
   *
   * A `<label>` wrapping a visually hidden `<input type="file">`: clicking
   * anywhere in the box opens the picker, because that is what a label does,
   * and the input stays in the accessibility tree and the tab order rather
   * than being replaced by a `div` with a click handler.
   *
   * `ondragover` must call `preventDefault`, or the browser navigates to the
   * dropped file instead of firing `ondrop`. That is the one non-obvious line
   * here, and it is why this cannot just be an `<input>`.
   */
  import type { Snippet } from 'svelte';

  interface Props {
    id?: string;
    multiple?: boolean;
    accept?: string;
    ondrop: (event: DragEvent) => void;
    onchange: (event: Event) => void;
    children: Snippet;
  }

  let { id, multiple = false, accept, ondrop, onchange, children }: Props = $props();

  let dragging = $state(false);

  function handleDrop(event: DragEvent) {
    dragging = false;
    ondrop(event);
  }
</script>

<label
  class="dropzone"
  class:dragging
  for={id}
  ondragover={(event) => {
    event.preventDefault();
    dragging = true;
  }}
  ondragleave={() => (dragging = false)}
  ondrop={handleDrop}
>
  {@render children()}
  <input {id} type="file" {multiple} {accept} {onchange} />
</label>

<style>
  .dropzone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 24px 16px;
    border: 2px dashed #4a4a4a;
    border-radius: 8px;
    background-color: #1f1f1f;
    text-align: center;
    cursor: pointer;
  }

  .dropzone:hover,
  .dropzone.dragging {
    border-color: var(--color-primary-500);
    background-color: #242424;
  }

  /* Visually hidden, not `display: none`: the input still has to be
     focusable and reachable by assistive technology. */
  input {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
  }

  .dropzone:focus-within {
    outline: 2px solid var(--color-primary-500);
    outline-offset: 2px;
  }
</style>
