<script lang="ts">
	import { SplitPane } from "@rich_harris/svelte-split-pane";
	import CodeMirror from "svelte-codemirror-editor";
	import { python } from "@codemirror/lang-python";
	import { oneDark } from "@codemirror/theme-one-dark";

	import Toolbar from "$lib/ui/Toolbar.svelte";
	import Terminal from "$lib/ui/Terminal.svelte";
	import FileBrowser from "$lib/ui/FileBrowser.svelte";
	import { currentFile, currentFileContent } from "$lib/stores/editor";
	const pageSize = "94vh";

	let fileBrowserComp;
</script>

<div class="page-container">
	<SplitPane type="horizontal" min="10%" max="15%" id="top">
		<section slot="a" id="browser">
			<FileBrowser bind:this={fileBrowserComp} />
		</section>
		<section slot="b" id="ide">
			<div id="codeMirror">
			{#if $currentFile != ""}
				<CodeMirror
					bind:value={$currentFileContent}
					lang={python()}
					theme={oneDark}
					on:change={fileBrowserComp.saveFile}
				/>
			{/if}
			</div>
		</section>
	</SplitPane>
	<Toolbar />
	<Terminal />
</div>

<style>
	#codeMirror {
		background-color: #242424;
		min-height: 60vh;
		max-height: 60vh;
		overflow: auto;
		position: relative;
	}
	.page-container {
		display: flex;
		flex-direction: column;
    	height: 94vh; /* 100vh - navBarSize */
		padding-top: 48px;
	}

</style>
