<script lang="ts">
  /**
   * A plain button, replacing flowbite's `Button`.
   *
   * Two variants, which is all the editor used: `primary` for the icon
   * buttons in the file browser's toolbar, and `alternative` for the
   * confirming button in a dialog footer. Everything else — `title`,
   * `disabled`, the click handler — is a normal attribute, forwarded with
   * `...rest`, so there is no wrapper API to remember.
   *
   * A disabled button here *looks* disabled. flowbite's did not, which is why
   * the old call sites had to pass `class="opacity-40 cursor-not-allowed"`
   * by hand and why a disabled run button used to look ready.
   */
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  interface Props extends HTMLButtonAttributes {
    variant?: 'primary' | 'alternative';
    children: Snippet;
  }

  let { variant = 'primary', children, ...rest }: Props = $props();
</script>

<button type="button" class={variant} {...rest}>
  {@render children()}
</button>

<style>
  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 7px 11px;
    border: 1px solid transparent;
    border-radius: 6px;
    font: inherit;
    font-size: 13px;
    line-height: 1;
    cursor: pointer;
  }

  button:focus-visible {
    outline: 2px solid var(--color-primary-500);
    outline-offset: 2px;
  }

  .primary {
    background-color: #3f3f46;
    color: #f4f4f5;
  }

  .primary:hover:not(:disabled) {
    background-color: #52525b;
  }

  .alternative {
    background-color: #262626;
    border-color: #52525b;
    color: #e4e4e7;
  }

  .alternative:hover:not(:disabled) {
    background-color: #333338;
  }

  button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
