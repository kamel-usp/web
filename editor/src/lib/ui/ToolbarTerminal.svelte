<script>
	import {
		Toolbar,
		ToolbarButton,
        CloseButton,
	} from "flowbite-svelte";
	import { PlayOutline, ChevronDownSolid } from "flowbite-svelte-icons";
	import { editorDpasp, editorPython, editorTerminal } from "$lib/stores/editor";
	import { get } from "svelte/store";
	import { Spinner } from "flowbite-svelte";

	let submitting = false;

    function close () {
        editorTerminal.set ("empty");
        console.log ("close");
    }
</script>


<Toolbar color="dark">
	<div class="flex-container">
	</div>
	<ToolbarButton name="send" slot="end" color="green" on:click={close}>
		<CloseButton class="w-1 h-1" />
	</ToolbarButton>
</Toolbar>

<style>
	.flex-container {
		display: flex;
		gap: 20px;
	}
</style>
