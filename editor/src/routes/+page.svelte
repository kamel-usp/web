<script lang="ts">
	import { SplitPane } from "@rich_harris/svelte-split-pane";
	import CodeMirror from "svelte-codemirror-editor";
	import { python } from "@codemirror/lang-python";
	import { oneDark } from "@codemirror/theme-one-dark";
	import { Button } from "flowbite-svelte";
	import { Tabs, TabItem } from "flowbite-svelte";
	import { ArrowRightOutline } from "flowbite-svelte-icons";

	import Toolbar from "$lib/ui/Toolbar.svelte";
	import Status from "$lib/ui/Status.svelte";
	import Terminal from "$lib/ui/Terminal.svelte";
	import { editor } from "$lib/stores/editor";

	import { signIn, signOut } from "@auth/sveltekit/client";
	import { page } from "$app/stores";

	const dividerThickness = "20px";
</script>

<SplitPane
	type="horizontal"
	min="100px"
	pos="70%"
	--thickness={dividerThickness}
>
	<section slot="a">
		<Tabs>
			<TabItem open>
				<span slot="title">HelloWorld.dpasp</span>
				<div id="codeMirror">
					<CodeMirror
						bind:value={$editor}
						lang={python()}
						theme={oneDark}
					/>
				</div>
			</TabItem>
		</Tabs>
		<Toolbar />
	</section>
	<section slot="b">
		<SplitPane type="vertical">
			<section slot="a" id="output"><Status /></section>
			<section slot="b" id="console"><Terminal /></section>
		</SplitPane>
	</section>
</SplitPane>

<h1>SvelteKit Auth Example</h1>
<p>
	{#if $page.data.session}
		{#if $page.data.session.user?.image}
			<span
				style="background-image: url('{$page.data.session.user.image}')"
				class="avatar"
			/>
		{/if}
		<span class="signedInText">
			<small>Signed in as</small><br />
			<strong>{$page.data.session.user?.name ?? "User"}</strong>
		</span>
		<button on:click={() => signOut()} class="button">Sign out</button>
	{:else}
		<span class="notSignedInText">You are not signed in</span>
		<button on:click={() => signIn("github")}>Sign In with GitHub</button>
	{/if}
</p>

<h1>Public</h1>
<a href="/signup">Login do Google</a>

<h1>Public</h1>
<a href="/protected">protected route</a>

<style>
	#codeMirror {
		background-color: #242424;
		min-height: 500px;
	}
</style>
