// /landing is retired. The page is redirected to the agent home at the hosting
// layer (see firebase.json), so it is no longer prerendered or served — the
// component is kept in code only. Setting prerender to false stops the build
// from emitting landing.html and its localized variants.
export const prerender = false;
