<script lang="ts">
	import { SplitPane } from '@rich_harris/svelte-split-pane';
	import CodeMirror from "svelte-codemirror-editor";
	import { python } from "@codemirror/lang-python";
	import { oneDark } from "@codemirror/theme-one-dark";
	import { Button } from 'flowbite-svelte';
	import { Tabs, TabItem } from 'flowbite-svelte';
	import { ArrowRightOutline } from 'flowbite-svelte-icons';

	import Toolbar from "$lib/ui/Toolbar.svelte";
	import Status from "$lib/ui/Status.svelte";
	import Terminal from "$lib/ui/Terminal.svelte";
	import { editor } from '$lib/stores/editor.ts';
	const dividerThickness = '20px';
</script>

<SplitPane type="horizontal" min="100px" pos="70%" --thickness={dividerThickness}>
	<section slot="a">
		<Tabs>
		  <TabItem open>
		    <span slot="title">HelloWorld.dpasp</span>
		    <div id="codeMirror"><CodeMirror bind:value={$editor} lang={python()} theme={oneDark} /></div>
		  </TabItem>
		</Tabs>
		<Toolbar/>
	</section>
	<section slot="b">
		<SplitPane type="vertical">
				<section slot="a" id="output"><Status /></section>
				<section slot="b" id="console"><Terminal /></section>
		</SplitPane>
	</section>
</SplitPane>

<style>
	#codeMirror {
		background-color: #242424; 
		min-height: 500px;
	}
</style>