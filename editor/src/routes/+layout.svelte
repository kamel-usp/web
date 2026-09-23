<script lang="ts">
	/**
	 * The page shell: a title bar, and the sign-in link when OAuth is
	 * configured.
	 *
	 * This used to be flowbite's `Navbar` with its `let:hidden let:toggle`
	 * slot props and a hamburger. There is one link in it, so the responsive
	 * menu it was collapsing into never had anything to collapse.
	 */
	import '../app.css';
	import { page } from '$app/state';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<nav>
	<a class="brand" href="/">dPASP Playground</a>

	<ul>
		<!-- The dPASP language tutorial. `target="_blank"` on purpose: the
		     playground holds unsaved buffers and a run in progress, and this
		     is the one link in the app that leaves it. -->
		<li>
			<a
				class="tutorial"
				href="https://kamel-usp.github.io/pages/learn_dpasp.html"
				target="_blank"
				rel="noopener noreferrer"
			>
				Learn dPASP
				<svg
					class="external"
					width="12"
					height="12"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2.2"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<path d="M14 4h6v6M20 4l-8.5 8.5M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
				</svg>
			</a>
		</li>

		<!-- Sign-in is only offered when OAuth credentials are configured;
		     otherwise every visitor gets an anonymous session and these routes
		     do not exist. -->
		{#if page.data.authEnabled}
			{#if page.data.session}
				<li class="user">{page.data.session.user?.name ?? 'User'}</li>
				<li><a class="auth" href="/auth/signout">Sign Out</a></li>
			{:else}
				<li><a class="auth" href="/auth/signin">Sign in</a></li>
			{/if}
		{/if}
	</ul>
</nav>

{@render children()}

<style>
	nav {
		position: fixed;
		inset: 0 0 auto 0;
		z-index: 40;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		height: var(--nav-height);
		padding: 0 16px;
		box-sizing: border-box;
		background-color: #111827;
		color: #e6e6e6;
	}

	.brand {
		white-space: nowrap;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--color-primary-500);
		text-decoration: none;
	}

	ul {
		display: flex;
		align-items: center;
		gap: 18px;
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 0.95rem;
	}

	.user {
		color: #cfcfcf;
	}

	.tutorial {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: #cfcfcf;
		text-decoration: none;
	}

	.tutorial:hover {
		color: #ffffff;
		text-decoration: underline;
	}

	.tutorial .external {
		opacity: 0.7;
	}

	.auth {
		color: #d4694a;
		text-decoration: none;
	}

	.auth:hover {
		text-decoration: underline;
	}

	a:focus-visible {
		outline: 2px solid var(--color-primary-500);
		outline-offset: 3px;
		border-radius: 3px;
	}
</style>
