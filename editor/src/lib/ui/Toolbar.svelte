<script>
	import {
		Toolbar,
		ToolbarButton,
		Button,
		Dropdown,
		Radio,
	} from "flowbite-svelte";
	import { PlayOutline, ChevronDownSolid } from "flowbite-svelte-icons";
	import { editorDpasp, editorPython, editorTerminal } from "$lib/stores/editor";
  	import { userID } from "$lib/stores/auth";
	import { get } from "svelte/store";
	import { Spinner } from "flowbite-svelte";

	import HoverMenu from "$lib/ui/HoverMenu/HoverMenu.svelte"
	import HoverMenuItem from "$lib/ui/HoverMenu/HoverMenuItem.svelte"

	let submitting = false;

	async function submit() {
		submitting = true;
		// TODO: send python code
		const code = get(editorDpasp);
		const sem = semantic_options["Semantics"][selected_semantics["Semantics"]]
		const psem = semantic_options["PSemantics"][selected_semantics["PSemantics"]]
		
    	const user_id = get(userID);
		const response = await fetch("/api/containermanager/run", {
			method: "POST",
			body: JSON.stringify({ sem, psem, code, user_id }),
			headers: {
				"content-type": "application/json",
			},
		});
		console.log(response.status);

		let res = await response.json();
		editorTerminal.set ("> " + (res.response == undefined ? "An error ocurred while processing your code." : res.response));
		submitting = false;
	}

	const semantic_options = {
		 "Semantics": [
			"stable",
			"partial",
			"lstable",
		 ],
		 "PSemantics": [
			"credal",
			"maxent",
		 ]
	}

	let selected_semantics = {}
	for (let k in semantic_options) {
		selected_semantics[k] = 0
	}
</script>


<Toolbar>
	<div class="flex-container">
		{#each Object.entries(semantic_options) as [sem, types] }
			<Button class="dark:bg-gray-900 text-primary-500 dark:hover:bg-gray-700">
				{sem}: {types[selected_semantics[sem]]}<ChevronDownSolid class="w-3 h-3 ml-2 text-white dark:text-white" />
			</Button>
			<Dropdown class="w-44 p-3 space-y-3 text-sm">
				{#each types.keys() as sem_ind}
					<li>
						<Radio name={sem} on:click={() => {selected_semantics[sem] = sem_ind;}}>{types[sem_ind]}</Radio>
					</li>
				{/each}
			</Dropdown>
		{/each}
	</div>
	<ToolbarButton name="send" slot="end" color="green" on:click={submit}>
		{#if submitting == false}
			<PlayOutline class="w-5 h-5" />
		{:else}
			<Spinner class="w-5 h-5" size={6} />
		{/if}
	</ToolbarButton>
</Toolbar>

<style>
	.flex-container {
		display: flex;
		gap: 20px;
	}
	.button {
		background-color: black;
	}
</style>
