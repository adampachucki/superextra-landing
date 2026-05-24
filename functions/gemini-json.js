import { GoogleAuth } from 'google-auth-library';

const VERTEX_BASE = 'https://aiplatform.googleapis.com';
const MODEL = 'gemini-2.5-flash-lite';

let _auth = null;

async function _getToken() {
	if (_auth === null) {
		_auth = new GoogleAuth({
			scopes: ['https://www.googleapis.com/auth/cloud-platform']
		});
	}
	const client = await _auth.getClient();
	const { token } = await client.getAccessToken();
	if (!token) throw new Error('failed to obtain access token');
	return token;
}

function _projectId() {
	return process.env.GOOGLE_CLOUD_PROJECT || process.env.GCLOUD_PROJECT || 'superextra-site';
}

function modelUrl() {
	return `${VERTEX_BASE}/v1/projects/${_projectId()}/locations/global/publishers/google/models/${MODEL}:generateContent`;
}

function extractText(payload) {
	return (
		payload?.candidates?.[0]?.content?.parts
			?.map((part) => (typeof part.text === 'string' ? part.text : ''))
			.join('')
			.trim() || ''
	);
}

export async function generateGeminiJson({
	prompt,
	responseSchema,
	maxOutputTokens,
	errorName,
	fetchImpl = fetch,
	getToken = _getToken
}) {
	const token = await getToken();
	const response = await fetchImpl(modelUrl(), {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			contents: [
				{
					role: 'user',
					parts: [{ text: prompt }]
				}
			],
			generationConfig: {
				temperature: 0,
				maxOutputTokens,
				responseMimeType: 'application/json',
				responseSchema,
				thinkingConfig: { thinkingBudget: 0 }
			}
		})
	});
	if (!response.ok) {
		const body = await response.text().catch(() => '');
		throw new Error(`${errorName}_failed:${response.status}:${body.slice(0, 200)}`);
	}

	const text = extractText(await response.json());
	try {
		return JSON.parse(text);
	} catch {
		throw new Error(`${errorName}_invalid_json`);
	}
}
