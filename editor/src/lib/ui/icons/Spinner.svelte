<script lang="ts">
  /**
   * The busy indicator, replacing flowbite's `Spinner`.
   *
   * It is the icon grid's three-quarter arc, spun by CSS. `prefers-reduced-
   * motion` stops the rotation rather than the indicator: someone who has
   * asked for less movement still needs to know the run is in flight, so the
   * arc stays on screen and holds still.
   */
  let { size = 20, class: className = '' }: { size?: number; class?: string } = $props();
</script>

<svg
  class="spinner {className}"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2.5"
  stroke-linecap="round"
  role="status"
  aria-label="Working"
  xmlns="http://www.w3.org/2000/svg"
>
  <path d="M12 3a9 9 0 1 0 9 9" />
</svg>

<style>
  .spinner {
    flex: none;
    animation: spin 0.9s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }
</style>
