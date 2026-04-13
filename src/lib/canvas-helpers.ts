export const CANVAS_COLORS: number[][] = [
	[110, 231, 183], // emerald
	[167, 139, 250], // violet
	[244, 114, 182], // pink
	[251, 191, 36], // amber
	[6, 182, 212], // cyan
	[99, 102, 241] // indigo
];

export function noise(t: number, seed: number): number {
	return (
		Math.sin(t * 0.67 + seed * 7.13) * 0.4 +
		Math.sin(t * 1.13 + seed * 3.37) * 0.35 +
		Math.sin(t * 0.31 + seed * 11.71) * 0.25
	);
}

export function lerp(a: number, b: number, t: number): number {
	return a + (b - a) * t;
}

export function lerpColor(a: number[], b: number[], t: number): number[] {
	return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
}

export function smoothstep(t: number): number {
	return t * t * (3 - 2 * t);
}
