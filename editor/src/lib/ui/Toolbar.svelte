<script>
	import { HomeOutline, EnvelopeOutline } from "flowbite-svelte-icons";
	import {
		Textarea,
		Toolbar,
		ToolbarGroup,
		ToolbarButton,
		Button,
	} from "flowbite-svelte";
	import { PlayOutline } from "flowbite-svelte-icons";
	import { editorDpasp, editorPython } from "$lib/stores/editor";
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
    const id = get(userID);
		const response = await fetch("/api/containermanager/run", {
			method: "POST",
			body: JSON.stringify({ sem, psem, code, id }),
			headers: {
				"content-type": "application/json",
			},
		});
		console.log(response.status);
		let res = await response.json();
		console.log(res);
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
	<!--	 <ToolbarGroup>
		<ToolbarButton name="Attach file"><PaperClipOutline class="w-5 h-5 rotate-45" /></ToolbarButton>
		<ToolbarButton name="Embed map"><MapPinAltSolid class="w-5 h-5" /></ToolbarButton>
		<ToolbarButton name="Upload image"><ImageOutline class="w-5 h-5" /></ToolbarButton>
	</ToolbarGroup> -->
	<ToolbarGroup>
			{#each Object.entries(semantic_options) as [sem, types] }
			<HoverMenu>
				<span slot="toggle">{sem}: {types[selected_semantics[sem]]}</span>
				{#each types.keys() as sem_ind}
					<HoverMenuItem>
					<button class="sem_selector" on:click={() => selected_semantics[sem] = sem_ind}>{types[sem_ind]}</button>
					</HoverMenuItem>
				{/each}
			</HoverMenu>
			{/each}
	</ToolbarGroup>
	<ToolbarButton name="send" slot="end" color="green" on:click={submit}>
		{#if submitting == false}
			<PlayOutline class="w-5 h-5" />
		{:else}
			<Spinner class="w-5 h-5" size={6} />
		{/if}
	</ToolbarButton>
</Toolbar>

<style>
	.sem_selector {
		padding: 0.5rem 1rem;
		width: 100%;
	}
</style>
