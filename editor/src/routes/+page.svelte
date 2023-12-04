<script lang="ts">
	import { SplitPane } from "@rich_harris/svelte-split-pane";
	import CodeMirror from "svelte-codemirror-editor";
	import { python } from "@codemirror/lang-python";
	import { oneDark } from "@codemirror/theme-one-dark";
	import { Tabs, TabItem} from "flowbite-svelte";
	import { ArrowRightOutline } from "flowbite-svelte-icons";

	import Toolbar from "$lib/ui/Toolbar.svelte";
	import Status from "$lib/ui/Status.svelte";
	import Terminal from "$lib/ui/Terminal.svelte";
	import FileBrowser from "$lib/ui/FileBrowser.svelte";
	import { editorDpasp, editorPython, editorTerminal } from "$lib/stores/editor";
	import { get } from "svelte/store";
    import ToolbarTerminal from "$lib/ui/ToolbarTerminal.svelte";

	const pageSize = "94vh";
</script>

<div class="page-container">
	{#if get (editorTerminal) != "epty"}
		<Tabs>
			<TabItem open>
				<span slot="title">Dpasp</span>
				<div id="codeMirrorError">
					<CodeMirror
						bind:value={$editorDpasp}
						placeholder="# Add your dPasp code"
						lang={python()}
						theme={oneDark}
					/>
				</div>
			</TabItem>
		</Tabs>
		<Toolbar />
		<ToolbarTerminal />
		<div id="console"><Terminal /></div>
	{:else}
		<Tabs>
			<TabItem open>
				<span slot="title">Dpasp</span>
				<div id="codeMirrorNormal">
					<CodeMirror
						bind:value={$editorDpasp}
						placeholder="# Add your dPasp code"
						lang={python()}
						theme={oneDark}
					/>
				</div>
			</TabItem>
		</Tabs>
		<Toolbar />
	{/if}
</div>
<FileBrowser />

<style>
	#codeMirrorError {
		background-color: #242424;
		min-height: 55vh;
		max-height: 55vh;
		overflow: auto;
		position: relative;
	}
	#codeMirrorNormal {
		background-color: #242424;
		min-height: 83vh;
		max-height: 83vh;
		overflow: auto;
		position: relative;
	}
	.page-container {
		display: flex;
		flex-direction: column;
    	height: 94vh; /* 100vh - navBarSize */
	}
</style>
