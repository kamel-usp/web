<script>
	import "../app.postcss";
	import { Navbar, NavBrand, NavLi, NavUl, NavHamburger } from 'flowbite-svelte';
	import { page } from "$app/stores";
</script>

<Navbar let:hidden let:toggle class="dark:bg-gray-900 fixed" style="color: #e6e6e6;">
	<NavBrand href="/">
		<span class="self-center whitespace-nowrap text-xl font-semibold dark:text-primary-500">dPASP Playground</span>
	</NavBrand>
	<NavHamburger on:click={toggle} />
	<NavUl {hidden}>
		<!-- Sign-in is only offered when OAuth credentials are configured;
		     otherwise every visitor gets an anonymous session. -->
		{#if $page.data.authEnabled}
			{#if $page.data.session}
				<NavLi>{$page.data.session.user?.name ?? "User"}</NavLi>
				<NavLi href="/auth/signout" style="color: #d4694a">Sign Out</NavLi>
			{:else}
				<NavLi href="/auth/signin" style="color: #d4694a">Sign in</NavLi>
			{/if}
		{/if}
	</NavUl>
</Navbar>

<slot />
