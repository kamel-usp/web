<script>
	import "../app.postcss";
	import SvelteTheme from 'svelte-themes/SvelteTheme.svelte';
	import { Navbar, NavBrand, NavLi, NavUl, NavHamburger } from 'flowbite-svelte';
    import { DarkMode } from 'flowbite-svelte';
	const navBarSize = "6vh";
</script>
<Navbar let:hidden let:toggle style="background-color: #2e2e2e; color: #e6e6e6; height: {navBarSize}">
	<NavBrand href="/">
		<span class="self-center whitespace-nowrap text-xl font-semibold dark:text-white">dPasp Playground</span>
	</NavBrand>
	<NavHamburger on:click={toggle} />
	<NavUl {hidden}>
		<!-- <NavLi href="/about" style="color: #d4694a">Sign in</NavLi> -->
		<NavLi style="color: #d4694a"><DarkMode /></NavLi>
	</NavUl>
</Navbar>

<SvelteTheme />
<slot />

<style>
</style>