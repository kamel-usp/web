<script>
	import "../app.postcss";
	import SvelteTheme from 'svelte-themes/SvelteTheme.svelte';
	import { Navbar, NavBrand, NavLi, NavUl, NavHamburger } from 'flowbite-svelte';
	import { page } from "$app/stores";
	import { onMount } from 'svelte';
	import { userID, loggedIn } from "$lib/stores/auth";
	import { get } from "svelte/store";
	import { makeid, hashid, setSessionID } from "$lib/auth";

	const navBarSize = "6vh";
	
	onMount(() => {
		setSessionID($page);
	});
</script>

<Navbar let:hidden let:toggle class="dark:bg-gray-900 fixed" style="color: #e6e6e6;">
	<NavBrand href="/">
		<span class="self-center whitespace-nowrap text-xl font-semibold dark:text-primary-500">dPasp Playground</span>
	</NavBrand>
	<NavHamburger on:click={toggle} />
	<NavUl {hidden}>
		<!-- <NavLi href="/about" style="color: #d4694a">Sign in</NavLi> -->
		{#if $page.data.session}
		<!-- 			{#if $page.data.session.user?.image}
				<span
					style="background-image: url('{$page.data.session.user.image}')"
					class="avatar"
				/>
			{/if} -->
			<NavLi>{$page.data.session.user?.name ?? "User"}</NavLi>
			<!-- <strong>{$page.data.session.user?.email ?? "Email"}</strong> -->
			<NavLi href="/auth/signout" style="color: #d4694a">Sign Out</NavLi>
		{:else}
			<NavLi href="/auth/signin" style="color: #d4694a">Sign in</NavLi>
		{/if}
		<!-- <NavLi style="color: #d4694a"><DarkMode /></NavLi> -->
	</NavUl>
</Navbar>

<SvelteTheme />
<slot />

<style>
</style>
