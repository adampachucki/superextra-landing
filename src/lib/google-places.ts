import { PUBLIC_GOOGLE_PLACES_KEY } from '$env/static/public';

export interface PlaceSuggestion {
	name: string;
	secondary: string;
	placeId: string;
}

let mapsPromise: Promise<void> | null = null;

export function loadGoogleMaps(): Promise<void> {
	if (mapsPromise) return mapsPromise;
	mapsPromise = new Promise<void>((resolve, reject) => {
		if (typeof google !== 'undefined' && google.maps?.places) {
			resolve();
			return;
		}
		const script = document.createElement('script');
		script.src = `https://maps.googleapis.com/maps/api/js?key=${PUBLIC_GOOGLE_PLACES_KEY}&libraries=places`;
		script.async = true;
		script.onload = () => resolve();
		script.onerror = reject;
		document.head.appendChild(script);
	});
	return mapsPromise;
}

export async function fetchPlaceSuggestions(
	input: string,
	regionCode: string
): Promise<PlaceSuggestion[]> {
	if (input.length < 2) return [];
	await loadGoogleMaps();
	const opts = {
		input,
		includedPrimaryTypes: ['restaurant', 'cafe', 'bar', 'hotel', 'food'],
		includedRegionCodes: [regionCode]
	};
	let { suggestions } = await // eslint-disable-next-line @typescript-eslint/no-explicit-any
	(google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(opts);
	// Retry without type filter when typed query (e.g. "name city") yields no results
	if (suggestions.length === 0) {
		// eslint-disable-next-line @typescript-eslint/no-unused-vars
		const { includedPrimaryTypes: _, ...fallbackOpts } = opts;
		({ suggestions } = await // eslint-disable-next-line @typescript-eslint/no-explicit-any
		(google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions(fallbackOpts));
	}
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	return suggestions.map((s: any) => ({
		name: s.placePrediction.mainText.text,
		secondary: s.placePrediction.secondaryText?.text ?? '',
		placeId: s.placePrediction.placeId
	}));
}
