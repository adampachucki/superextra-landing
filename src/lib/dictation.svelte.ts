let active = $state(false);
let supported = $state(false);
let volume = $state(0);
let interim = $state('');
let recognition: SpeechRecognition | null = null;
let onResult: ((text: string) => void) | null = null;
let audioCtx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
let mediaStream: MediaStream | null = null;
let rafId = 0;

if (typeof window !== 'undefined') {
	const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
	supported = !!SR;
	if (SR) {
		recognition = new SR();
		recognition.continuous = true;
		recognition.interimResults = true;
		recognition.onresult = (e) => {
			let finalText = '';
			let interimText = '';
			for (let i = 0; i < e.results.length; i++) {
				const result = e.results[i];
				if (result.isFinal) {
					finalText += result[0].transcript;
				} else {
					interimText += result[0].transcript;
				}
			}
			if (finalText && onResult) {
				onResult(finalText);
				interim = '';
			} else {
				interim = interimText;
			}
		};
		recognition.onend = () => {
			active = false;
			interim = '';
			stopAudio();
		};
		recognition.onerror = () => {
			active = false;
			interim = '';
			stopAudio();
		};
	}
}

function startAudio() {
	navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
		mediaStream = stream;
		audioCtx = new AudioContext();
		analyser = audioCtx.createAnalyser();
		analyser.fftSize = 256;
		analyser.smoothingTimeConstant = 0.5;
		const source = audioCtx.createMediaStreamSource(stream);
		source.connect(analyser);
		pollVolume();
	}).catch(() => {});
}

function pollVolume() {
	if (!analyser) return;
	const data = new Uint8Array(analyser.frequencyBinCount);
	analyser.getByteFrequencyData(data);
	let sum = 0;
	for (let i = 0; i < data.length; i++) sum += data[i];
	volume = Math.min(1, (sum / data.length) / 80);
	rafId = requestAnimationFrame(pollVolume);
}

function stopAudio() {
	cancelAnimationFrame(rafId);
	volume = 0;
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
	get interim() {
		return interim;
	},
	toggle(callback: (text: string) => void) {
		if (!recognition) return;
		if (active) {
			recognition.stop();
			active = false;
			interim = '';
			stopAudio();
		} else {
			onResult = callback;
			recognition.start();
			active = true;
			startAudio();
		}
	},
	stop() {
		if (recognition && active) {
			recognition.stop();
			active = false;
			interim = '';
			stopAudio();
		}
	}
};
