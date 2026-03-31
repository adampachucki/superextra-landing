let playingIndex = $state<number | null>(null);
let loading = $state<number | null>(null);
let audio: HTMLAudioElement | null = null;

function stop() {
	if (audio) {
		audio.onended = null;
		audio.onerror = null;
		audio.pause();
		audio.removeAttribute('src');
		audio.load();
		audio = null;
	}
	playingIndex = null;
	loading = null;
}

async function play(messageIndex: number, text: string) {
	if (playingIndex === messageIndex) {
		stop();
		return;
	}

	stop();
	loading = messageIndex;

	try {
		const res = await fetch('/api/tts', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ text })
		});

		if (!res.ok) {
			const err = await res.json().catch(() => ({ error: 'Speech synthesis failed' }));
			console.error('TTS error:', err.error);
			return;
		}

		const blob = await res.blob();
		const url = URL.createObjectURL(blob);

		audio = new Audio(url);
		audio.onended = () => {
			URL.revokeObjectURL(url);
			playingIndex = null;
			audio = null;
		};

		await audio.play();
		playingIndex = messageIndex;
	} catch (err) {
		console.error('TTS failed:', err);
		if (audio) {
			audio.onended = null;
			audio.pause();
			audio = null;
		}
	} finally {
		loading = null;
	}
}

export const tts = {
	get playingIndex() {
		return playingIndex;
	},
	get loading() {
		return loading;
	},
	play,
	stop
};
