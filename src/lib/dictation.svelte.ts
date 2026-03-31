const WS_URL = 'wss://api.elevenlabs.io/v1/speech-to-text/realtime';
const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

let active = $state(false);
let supported = $state(false);
let volume = $state(0);
let text = $state('');

let connecting = false;
let ws: WebSocket | null = null;
let audioCtx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
let processor: ScriptProcessorNode | null = null;
let mediaStream: MediaStream | null = null;
let rafId = 0;

let commits: string[] = [];
let partial = '';

if (typeof window !== 'undefined') {
	supported = !!navigator.mediaDevices?.getUserMedia;
}

function updateText() {
	const parts = [...commits];
	if (partial) parts.push(partial);
	text = parts.join(' ');
}

function float32ToPcm16Base64(float32: Float32Array): string {
	const buffer = new ArrayBuffer(float32.length * 2);
	const view = new DataView(buffer);
	for (let i = 0; i < float32.length; i++) {
		const s = Math.max(-1, Math.min(1, float32[i]));
		view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
	}
	const bytes = new Uint8Array(buffer);
	let binary = '';
	for (let i = 0; i < bytes.length; i++) {
		binary += String.fromCharCode(bytes[i]);
	}
	return btoa(binary);
}

function pollVolume() {
	if (!analyser) return;
	const data = new Uint8Array(analyser.frequencyBinCount);
	analyser.getByteFrequencyData(data);
	let sum = 0;
	for (let i = 0; i < data.length; i++) sum += data[i];
	volume = Math.min(1, sum / data.length / 80);
	rafId = requestAnimationFrame(pollVolume);
}

function cleanup() {
	cancelAnimationFrame(rafId);
	volume = 0;
	partial = '';
	commits = [];

	if (ws) {
		ws.onmessage = null;
		ws.onerror = null;
		ws.onclose = null;
		if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
			ws.close();
		}
		ws = null;
	}

	if (processor) {
		processor.disconnect();
		processor = null;
	}

	if (audioCtx) {
		audioCtx.close();
		audioCtx = null;
		analyser = null;
	}

	if (mediaStream) {
		mediaStream.getTracks().forEach((t) => t.stop());
		mediaStream = null;
	}
}

async function start() {
	if (connecting || active) return;
	connecting = true;
	commits = [];
	partial = '';
	text = '';

	try {
		const tokenRes = await fetch('/api/stt-token', { method: 'POST' });
		const tokenData = await tokenRes.json();
		if (!tokenData.ok || !tokenData.token) {
			throw new Error(tokenData.error || 'Failed to get speech token');
		}

		mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

		audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
		analyser = audioCtx.createAnalyser();
		analyser.fftSize = 256;
		analyser.smoothingTimeConstant = 0.5;

		const source = audioCtx.createMediaStreamSource(mediaStream);
		source.connect(analyser);

		processor = audioCtx.createScriptProcessor(BUFFER_SIZE, 1, 1);
		processor.onaudioprocess = (e) => {
			if (ws?.readyState === WebSocket.OPEN) {
				const pcm = e.inputBuffer.getChannelData(0);
				ws.send(
					JSON.stringify({
						message_type: 'input_audio_chunk',
						audio_base_64: float32ToPcm16Base64(pcm)
					})
				);
			}
		};
		source.connect(processor);
		processor.connect(audioCtx.destination);

		pollVolume();

		const params = new URLSearchParams({
			token: tokenData.token,
			model_id: 'scribe_v2_realtime',
			audio_format: `pcm_${SAMPLE_RATE}`,
			commit_strategy: 'vad',
			include_language_detection: 'true'
		});

		ws = new WebSocket(`${WS_URL}?${params}`);

		ws.onmessage = (e) => {
			try {
				const msg = JSON.parse(e.data);
				if (msg.message_type === 'partial_transcript') {
					partial = msg.text || '';
					updateText();
				} else if (msg.message_type === 'committed_transcript') {
					const chunk = msg.text?.trim();
					if (chunk) commits.push(chunk);
					partial = '';
					updateText();
				} else if (
					msg.message_type === 'auth_error' ||
					msg.message_type === 'quota_exceeded' ||
					msg.message_type === 'rate_limited'
				) {
					console.error('ElevenLabs STT error:', msg.message_type, msg.error);
					stop();
				}
			} catch {
				// ignore malformed WebSocket messages
			}
		};

		ws.onerror = () => stop();
		ws.onclose = () => {
			if (active) stop();
		};

		active = true;
	} catch (err) {
		console.error('Dictation start failed:', err);
		cleanup();
	} finally {
		connecting = false;
	}
}

function stop() {
	active = false;
	connecting = false;
	cleanup();
}

export const dictation = {
	get active() {
		return active;
	},
	get supported() {
		return supported;
	},
	get volume() {
		return volume;
	},
	get text() {
		return text;
	},
	toggle() {
		if (active || connecting) stop();
		else start();
	},
	stop
};
