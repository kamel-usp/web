<script lang="ts">
  /**
   * The one icon component. Every icon in the editor is a short path drawn on
   * the same 24×24 grid, so the shared parts — the viewBox, `currentColor`,
   * the stroke settings, `aria-hidden` — live here and each icon is a `d`
   * attribute.
   *
   * These replaced `flowbite-svelte-icons`. That package existed to supply
   * five glyphs, and it was one of the dependency chains `npm audit` kept
   * reporting, because it pinned Svelte 4.
   *
   * `fill` is for the solid glyphs (file, upload, download); the outline ones
   * (play, sliders) stroke instead. `size` is in pixels and matches what the
   * Tailwind classes used to set.
   */
  interface Props {
    /** The path data, from `$lib/ui/icons/paths`. */
    d: string;
    /** Solid glyph rather than a stroked outline. */
    solid?: boolean;
    size?: number;
    class?: string;
    title?: string;
  }

  let { d, solid = false, size = 20, class: className = '', title }: Props = $props();
</script>

<svg
  class={className}
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill={solid ? 'currentColor' : 'none'}
  stroke={solid ? 'none' : 'currentColor'}
  stroke-width={solid ? 0 : 2}
  stroke-linecap="round"
  stroke-linejoin="round"
  role={title ? 'img' : 'presentation'}
  aria-hidden={title ? undefined : 'true'}
  aria-label={title}
  xmlns="http://www.w3.org/2000/svg"
>
  {#if title}<title>{title}</title>{/if}
  <path {d} />
</svg>

<style>
  svg {
    flex: none;
  }
</style>
