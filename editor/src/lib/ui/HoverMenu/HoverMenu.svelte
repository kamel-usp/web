<div>
	<button><slot name="toggle" /></button>
	<menu><slot /></menu>
</div>

<style>
	div {
		transition: all 0.5s ease;
		height: 100%
	}

	button {
		border: none;
		background-color: inherit;
		display: block;
	}

	menu {
		position: absolute;
		transform: translateY(0.05em);
		margin-block-start: 0;
		padding: 0;
		border: 1px solid black;
		background-color: black;
		overflow: hidden;

		display: none;
		opacity: 0;
		visibility: hidden;
	}

	div:hover > menu {
		display: block;
		opacity: 1;
		visibility: visible;
	}
</style>
