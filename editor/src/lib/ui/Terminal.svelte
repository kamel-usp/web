<script lang="ts">
	import CodeMirror from "svelte-codemirror-editor";
	import { html } from "@codemirror/lang-html";
	import { editorTerminal } from "$lib/stores/editor";
	import { oneDark } from "@codemirror/theme-one-dark";
</script>

<div id="codeMirror">
    <CodeMirror
        bind:value={$editorTerminal}
        placeholder="> "
        lang={html()}
        theme={oneDark}
        readonly={true}
    />
</div>

<style>
	#codeMirror {
		background-color: #222222;
		min-height: 28.3vh;
		max-height: 28.3vh;
		overflow: auto;
		position: relative;
	}
</style>

