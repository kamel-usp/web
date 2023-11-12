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
	import { editorDpasp, editorPython } from "$lib/stores/editor";

	const pageSize = "94vh";
</script>

<div class="page-container">
	<Tabs>
		<TabItem open>
			<span slot="title">Dpasp</span>
			<div id="codeMirror">
				<CodeMirror
					bind:value={$editorDpasp}
					placeholder="# Add your dPasp code"
					lang={python()}
					theme={oneDark}
				/>
			</div>
		</TabItem>
		<TabItem open>
			<span slot="title">Python</span>
			<div id="codeMirror">
				<CodeMirror
					bind:value={$editorPython}
					placeholder="# Add your python code"
					lang={python()}
					theme={oneDark}
				/>
			</div>
		</TabItem>
	</Tabs>
	<Toolbar />
	<SplitPane type="horizontal" min="30%" max="70%" >
		<section slot="a" id="console"><Terminal /></section>
		<section slot="b" id="output"><Status /></section>
	</SplitPane>
</div>
<FileBrowser />

<style>
	#codeMirror {
		background-color: #242424;
		min-height: 55vh;
		max-height: 55vh;
		overflow: auto;
		position: relative;
	}
	.page-container {
		display: flex;
		flex-direction: column;
    	height: 94vh; /* 100vh - navBarSize */
	}
</style>
