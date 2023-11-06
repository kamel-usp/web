<script>
	import "../app.postcss";
	import SvelteTheme from 'svelte-themes/SvelteTheme.svelte';
	import { Navbar, NavBrand, NavLi, NavUl, NavHamburger } from 'flowbite-svelte';
    import { DarkMode } from 'flowbite-svelte';
    import { signIn, signOut } from "@auth/sveltekit/client";
	import { page } from "$app/stores";
	import { userID } from "$lib/stores/auth";
	import { get } from "svelte/store";
	import { makeid, hashid } from "$lib/auth";
	
	// from: https://stackoverflow.com/a/40031979/9014097
	function buf2hex(buffer) { // buffer is an ArrayBuffer
	    return Array.prototype.map.call(new Uint8Array(buffer), x => ('00' + x.toString(16)).slice(-2)).join('');
	}
	async function setSessionID() {
    	var id = makeid(24);
    	if ($page.data?.session?.user.email == undefined) id = await hashid(id);
    	else id = await hashid($page.data?.session?.user.email);
    	userID.set(buf2hex(id));
	}
	setSessionID();
	
</script>

<Navbar let:hidden let:toggle style="background-color: #2e2e2e; color: #e6e6e6">
	<NavBrand href="/">
		<span class="self-center whitespace-nowrap text-xl font-semibold dark:text-white">dPasp Playground</span>
	</NavBrand>
	<NavHamburger on:click={toggle} />
	<NavUl {hidden}>
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