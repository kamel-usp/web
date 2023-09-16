<script lang="ts">
	import { SplitPane } from '@rich_harris/svelte-split-pane';
	import CodeMirror from "svelte-codemirror-editor";
	import { python } from "@codemirror/lang-python";
	import { oneDark } from "@codemirror/theme-one-dark";
	import { Button } from 'flowbite-svelte';
	import { Tabs, TabItem } from 'flowbite-svelte';
	import { ArrowRightOutline } from 'flowbite-svelte-icons';

	import Toolbar from "$lib/ui/Toolbar.svelte";

	let value = "";
	const dividerThickness = '20px';
</script>

<SplitPane type="horizontal" min="100px" pos="70%" --thickness={dividerThickness} style="max-width: none !important;">
	<section slot="a">
		<Tabs>
		  <TabItem open>
		    <span slot="title">HelloWorld.dpasp</span>
		    <div id="codeMirror"><CodeMirror bind:value lang={python()} theme={oneDark} /></div>
		  </TabItem>
		</Tabs>
		<Toolbar/>
	</section>
	<section slot="b">
		<SplitPane type="vertical">
				<section slot="a" id="output">
					<div class="placeholder-circle w-16" />
				</section>
				<section slot="b" id="console">&nbsp;$</section>
		</SplitPane>
	</section>
</SplitPane>

<style>
	#codeMirror {
		background-color: #242424; 
		min-height: 500px;
	}
</style>