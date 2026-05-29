<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/auth.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import LoginForm from './LoginForm.svelte';

	let mounted = $state(false);

	onMount(() => {
		// Kick auth init so onAuthStateChanged is wired before the user clicks.
		void auth.init();
		mounted = true;
	});

	// When auth resolves to signed-in while the modal is open, fire the queued
	// callback (if any) and close. Consume the saved draft too — the
	// modal path uses the closure-captured prompt, so a leftover draft
	// would otherwise be picked up by a later visit to /login.
	$effect(() => {
		if (!auth.modalVisible) return;
		if (auth.status !== 'signed-in') return;
		const cb = auth.consumeAfterSignIn();
		auth.consumeDraft();
		auth.closeModal();
		if (cb) cb();
	});
</script>

<Modal
	open={auth.modalVisible && mounted}
	onclose={() => auth.closeModal()}
	ariaLabel="Sign in to Superextra"
>
	<div class="p-6">
		<LoginForm returnTo={auth.modalReturnTo} />
	</div>
</Modal>
