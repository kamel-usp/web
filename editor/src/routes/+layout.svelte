<script>
  import "../app.postcss";
  import SvelteTheme from 'svelte-themes/SvelteTheme.svelte';
  import { Navbar, NavBrand, NavLi, NavUl, NavHamburger } from 'flowbite-svelte';
</script>
<Navbar let:hidden let:toggle style="background-color: #1c1b21;">
  <NavBrand href="/">
    <span class="self-center whitespace-nowrap text-xl font-semibold dark:text-white">dPasp Playground</span>
  </NavBrand>
  <NavHamburger on:click={toggle} />
  <NavUl {hidden}>
    <NavLi href="/about">Sign in</NavLi>
  </NavUl>
</Navbar>

<SvelteTheme />
<slot />

<style>
</style>