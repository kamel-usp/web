<script>
	import "../app.postcss";
	import SvelteTheme from 'svelte-themes/SvelteTheme.svelte';
	import { Button, Navbar, NavBrand, NavLi, NavUl, NavHamburger, Modal, Dropzone } from 'flowbite-svelte';
    import { DarkMode } from 'flowbite-svelte';
    import { signIn, signOut } from "@auth/sveltekit/client";
	import { page } from "$app/stores";
	import { userID } from "$lib/stores/auth";
	import { get } from "svelte/store";
	import { makeid, hashid } from "$lib/auth";
	
	const navBarSize = "6vh";
	let clickOutsideModal = false;

	// from: https://stackoverflow.com/a/40031979/9014097
	function buf2hex(buffer) { // buffer is an ArrayBuffer
	    return Array.prototype.map.call(new Uint8Array(buffer), x => ('00' + x.toString(16)).slice(-2)).join('');
	}
	async function setSessionID() {
    	var id = makeid(24);
    	if ($page.data?.session?.user.email == undefined) id = await hashid(id);
    	else id = await hashid($page.data?.session?.user.email);
    	userID.set(buf2hex(id));
	}

	let value = [];
	const dropHandle = (event) => {
	  value = [];
	  event.preventDefault();
	  if (event.dataTransfer.items) {
	    [...event.dataTransfer.items].forEach((item, i) => {
	      if (item.kind === 'file') {
	        const file = item.getAsFile();
	        value.push(file.name);
	        value = value;
	      }
	    });
	  } else {
	    [...event.dataTransfer.files].forEach((file, i) => {
	      value = file.name;
	    });
	  }
	};

	const handleChange = (event) => {
	  const files = event.target.files;
	  if (files.length > 0) {
	    value.push(files[0].name);
	    value = value;
	  }
	};

	const showFiles = (files) => {
	  if (files.length === 1) return files[0];
	  let concat = '';
	  files.map((file) => {
	    concat += file;
	    concat += ',';
	    concat += ' ';
	  });

	  if (concat.length > 40) concat = concat.slice(0, 40);
	  concat += '...';
	  return concat;
	};

	// async function uploadFile() {
	// 	const id = get(userID);
	// 	const response = await fetch("/api/instance/add", {
	// 		method: "POST",
	// 		body: JSON.stringify({ sem, psem, code, id }),
	// 		headers: {
	// 			"content-type": "application/json",
	// 		},
	// 	});
	// 	console.log(response.status);
	// 	let res = await response.json();
	// 	console.log(res);
	// 	submitting = false;
	// }
	setSessionID();
	
</script>
<Navbar let:hidden let:toggle style="background-color: #2e2e2e; color: #e6e6e6; height: {navBarSize}">
	<NavBrand href="/">
		<span class="self-center whitespace-nowrap text-xl font-semibold dark:text-white">dPasp Playground</span>
	</NavBrand>
	<NavHamburger on:click={toggle} />
	<NavUl {hidden}>
		<!-- <NavLi href="/about" style="color: #d4694a">Sign in</NavLi> -->
		{#if $page.data.session}
		<!-- 			{#if $page.data.session.user?.image}
				<span
					style="background-image: url('{$page.data.session.user.image}')"
					class="avatar"
				/>
			{/if} -->
			<NavLi>{$page.data.session.user?.name ?? "User"}</NavLi>
			<!-- <strong>{$page.data.session.user?.email ?? "Email"}</strong> -->
			<NavLi href="/auth/signout" style="color: #d4694a">Sign Out</NavLi>
		{:else}
			<NavLi href="/auth/signin" style="color: #d4694a">Sign in</NavLi>
		{/if}
		<!-- <NavLi style="color: #d4694a"><DarkMode /></NavLi> -->
	</NavUl>
</Navbar>

<Button on:click={() => (clickOutsideModal = true)}>Default modal</Button>
<Modal title="File upload" bind:open={clickOutsideModal} autoclose outsideclose>
  <Dropzone
    id="dropzone"
    on:drop={dropHandle}
    on:dragover={(event) => {
      event.preventDefault();
    }}
    on:change={handleChange}>
    <svg aria-hidden="true" class="mb-3 w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
    {#if value.length === 0}
      <p class="mb-2 text-sm text-gray-500 dark:text-gray-400"><span class="font-semibold">Click to upload</span> or drag and drop</p>
      <p class="text-xs text-gray-500 dark:text-gray-400">SVG, PNG, JPG or GIF (MAX. 800x400px)</p>
    {:else}
      <p>{showFiles(value)}</p>
    {/if}
  </Dropzone>
  <svelte:fragment slot="footer">
    <Button color="alternative">Ok</Button>
  </svelte:fragment>
</Modal>

<SvelteTheme />
<slot />

<style>
</style>