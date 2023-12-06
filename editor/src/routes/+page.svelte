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
	import { currentFile, fileContents } from "$lib/stores/editor";
	import { get } from "svelte/store";
	const pageSize = "94vh";

	async function uploadFile(filename, content) {
	  const response = await fetch("/api/instance/blob/upload", {
	    method: "POST",
	    body: JSON.stringify({ filename, content }),
	    headers: {
	      "content-type": "application/json",
	    },
	  });
	  let res = await response.json();
	}

	async function saveFile() {
	  const content = $fileContents[$currentFile]
	  const filename = $currentFile
	  await uploadFile(filename, content);
	}
</script>

<div class="page-container">
	<SplitPane type="horizontal" min="10%" max="15%" id="top">
		<section slot="a" id="browser">
			<FileBrowser />
		</section>
		<section slot="b" id="ide">
			<div id="codeMirror">
			<CodeMirror
					bind:value={$fileContents[$currentFile]}
					lang={python()}
					theme={oneDark}
					on:change={saveFile}
			/>
			</div>
		</section>
	</SplitPane>
	<Toolbar />
	<SplitPane type="horizontal" min="30%" max="70%"  id="bottom">
		<section slot="a" id="console"><Terminal /></section>
		<section slot="b" id="output"><Status /></section>
	</SplitPane>
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
	}

</style>
