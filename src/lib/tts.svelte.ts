let playingIndex = $state<number | null>(null);
let loading = $state<number | null>(null);
let ctx: AudioContext | null = null;
let sourceNode: AudioBufferSourceNode | null = null;

function stop() {
	if (sourceNode) {
		sourceNode.onended = null;
		sourceNode.stop();
		sourceNode.disconnect();
		sourceNode = null;
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

	// Unlock audio on Safari: create/resume AudioContext synchronously in the click handler
	if (!ctx) ctx = new AudioContext();
	if (ctx.state === 'suspended') ctx.resume();

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

		const arrayBuffer = await res.arrayBuffer();
		const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

		sourceNode = ctx.createBufferSource();
		sourceNode.buffer = audioBuffer;
		sourceNode.connect(ctx.destination);
		sourceNode.onended = () => {
			sourceNode = null;
			playingIndex = null;
		};
		sourceNode.start();
		playingIndex = messageIndex;
	} catch (err) {
		console.error('TTS failed:', err);
		if (sourceNode) {
			sourceNode.onended = null;
			sourceNode.stop();
			sourceNode.disconnect();
			sourceNode = null;
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
