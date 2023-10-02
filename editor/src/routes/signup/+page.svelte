<script lang="ts">
    export let form;
    import { SplitPane } from "@rich_harris/svelte-split-pane";
    import CodeMirror from "svelte-codemirror-editor";
    import { python } from "@codemirror/lang-python";
    import { oneDark } from "@codemirror/theme-one-dark";
    import { Button } from "flowbite-svelte";
    import { Tabs, TabItem } from "flowbite-svelte";
    import { ArrowRightOutline } from "flowbite-svelte-icons";

    import Toolbar from "$lib/ui/Toolbar.svelte";
    import Status from "$lib/ui/Status.svelte";
    import Terminal from "$lib/ui/Terminal.svelte";
    import { editor } from "$lib/stores/editor";

    import { signIn, signOut } from "@auth/sveltekit/client";
    import { page } from "$app/stores";

    const dividerThickness = "20px";
</script>

<div class="sign-in-wrapper">
    <div class="sign-in-content">
        <h2>Sign Up to dPasp Editor!</h2>
        <form class="auth-form" method="post" action="?/OAuth2">
            <div>
                <button class="btn-auth" type="submit">
                    <img
                        class="btn-auth-img"
                        src="/google_signin_buttons/web/1x/btn_google_signin_dark_pressed_web.png"
                        alt="google sign in"
                    />
                </button>
            </div>
        </form>
    </div>
</div>
<h1>SvelteKit Auth Example</h1>
<p>
    {#if $page.data.session}
        {#if $page.data.session.user?.image}
            <span
                style="background-image: url('{$page.data.session.user.image}')"
                class="avatar"
            />
        {/if}
        <span class="signedInText">
            <small>Signed in as</small><br />
            <strong>{$page.data.session.user?.name ?? "User"}</strong>
        </span>
        <button on:click={() => signOut()} class="button">Sign out</button>
    {:else}
        <span class="notSignedInText">You are not signed in</span>
        <button on:click={() => signIn("github")}>Sign In with GitHub</button>
    {/if}
</p>

<style>
    div {
        color: #000000;
        margin-bottom: 0.5em;
        text-shadow: 0 0 2px #ffffff;
    }

    button {
        width: 100%;
        background-color: #fff;
        transition: all 0.3s ease-in;
    }
    button:hover {
        cursor: pointer;
        text-decoration: underline;
        color: #fff;
        background-color: #4d4c4c;
        transition: all 0.3s ease-in;
    }

    .btn-auth-img:hover {
        box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.5);
    }
    .btn-auth {
        border: 0;
        background-color: rgba(84, 81, 81, 0);
        padding: 0.01em;
    }
    .btn-auth:hover {
        border: 0;
        padding: 0.01em;
        text-decoration: none;
        background-color: rgba(84, 81, 81, 0);
    }
    .auth-form {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
    }
    .sign-in-wrapper {
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        align-items: center;
        height: 100vh;
        width: 100%;
        background-size: cover;
        background-position: center center;
        background-repeat: no-repeat;
    }
    .sign-in-content {
        max-width: 350px;
        background-color: rgba(84, 81, 81, 0.35);
        padding: 1em;
        border-radius: 5px;
    }

    .sign-in-wrapper {
        height: 100vh;
    }
</style>
