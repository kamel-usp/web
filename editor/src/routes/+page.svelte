<script lang="ts">
	import { SplitPane } from '@rich_harris/svelte-split-pane';
	import CodeMirror from "svelte-codemirror-editor";
	import { python } from "@codemirror/lang-python";
	import { oneDark } from "@codemirror/theme-one-dark";
	import { Button } from 'flowbite-svelte';
	import Toolbar from "$lib/ui/Toolbar.svelte";
	let value = "";
	const dividerThickness = '20px';
</script>

<div class="main-container">
	<SplitPane type="horizontal" min="100px" pos="70%" --thickness={dividerThickness}>
		<section slot="a" id="codeMirror">
			<CodeMirror bind:value lang={python()} theme={oneDark}/>
			<!-- <SplitPane type="vertical" pos="10%">
				<section slot="a">
					<Toolbar/>
				</section>
				<section slot="b" id="codeMirror">
					<CodeMirror bind:value lang={javascript()} theme={oneDark}/>	
				</section>
			</SplitPane> -->
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
</div>

<style>
	#codeMirror {
	  background-color: #292c33; 
	  height: 600px;
	}
	#console {
	  background-color: black; 
	}
	#output {
	  background-color: #1c1b21; 
	}
</style>