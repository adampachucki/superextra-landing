import { GoogleAuth } from 'google-auth-library';

let auth = null;

/**
 * Fetch a cloud-platform access token for Vertex AI REST calls.
 * The GoogleAuth client is cached across calls within the function instance.
 */
export async function getVertexAccessToken() {
	if (auth === null) {
		auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
	}
	const client = await auth.getClient();
	const { token } = await client.getAccessToken();
	if (!token) throw new Error('failed to obtain access token');
	return token;
}
