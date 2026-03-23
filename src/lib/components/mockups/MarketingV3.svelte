<div class="feed">

	<!-- Instagram post -->
	<div class="post post-light">
		<div class="platform-badge ig-badge">
			<svg width="12" height="12" viewBox="0 0 24 24" fill="none">
				<rect x="2" y="2" width="20" height="20" rx="5" fill="url(#ig-g)"/>
				<circle cx="12" cy="12" r="4.5" stroke="white" stroke-width="1.5" fill="none"/>
				<circle cx="17.5" cy="6.5" r="1.2" fill="white"/>
				<defs><linearGradient id="ig-g" x1="2" y1="22" x2="22" y2="2"><stop offset="0%" stop-color="#f59e0b"/><stop offset="50%" stop-color="#ec4899"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient></defs>
			</svg>
		</div>
		<div class="post-image" style="background: linear-gradient(135deg, #f59e0b, #ec4899); width: 48px; height: 48px;"></div>
		<div class="post-body">
			<span class="post-handle">@theburgerbar</span>
			<span class="post-caption">Double smash, secret sauce…</span>
			<span class="post-metrics">♥ 2.8K &nbsp; 💬 142</span>
		</div>
	</div>

	<!-- TikTok post -->
	<div class="post post-light">
		<div class="platform-badge tt-badge">
			<svg width="12" height="12" viewBox="0 0 24 24" fill="none">
				<rect width="24" height="24" rx="5" fill="#0a0a0a"/>
				<path d="M16.5 8c.7.8 1.7 1.3 2.5 1.3v2.2c-.7 0-1.5-.3-2.2-.7v4.2a3.5 3.5 0 11-3.5-3.5v2.2a1.3 1.3 0 101.3 1.3V5.5h2.2c0 .8.1 1.6.4 2.2z" fill="white"/>
			</svg>
		</div>
		<div class="post-image tt-image" style="background: linear-gradient(180deg, #1a1a2e, #6366f1); width: 48px; height: 64px;">
			<span class="play-icon">▶</span>
		</div>
		<div class="post-body">
			<span class="post-handle">@theburgerbar</span>
			<span class="post-views post-views-dark">14.2K views</span>
			<span class="post-metrics">♥ 4.2K &nbsp; 💬 318</span>
		</div>
	</div>

	<!-- Facebook post -->
	<div class="post post-light">
		<div class="platform-badge fb-badge">
			<svg width="12" height="12" viewBox="0 0 24 24" fill="none">
				<rect width="24" height="24" rx="5" fill="#1877f2"/>
				<path d="M13.5 8H16V5.5h-2.5C11.5 5.5 10 7 10 9v1.5H8V13h2v8h3v-8h2l.5-2.5H13V9c0-.6.2-1 .5-1z" fill="white"/>
			</svg>
		</div>
		<div class="post-image" style="background: linear-gradient(135deg, #06b6d4, #6ee7b7); width: 48px; height: 48px;"></div>
		<div class="post-body">
			<span class="post-handle">The Burger Bar</span>
			<span class="sponsored-pill">Sponsored</span>
			<span class="post-metrics">342 reactions · 48 comments</span>
		</div>
	</div>

</div>

<style>
	.feed {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 0.75rem 1.25rem;
	}

	/* ── Post card base ── */
	.post {
		position: relative;
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		gap: 0.625rem;
		padding: 0.625rem;
		border-radius: 10px;
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
		flex-shrink: 0;
	}

	.post-light {
		background: #ffffff;
	}

	/* ── Platform badge ── */
	.platform-badge {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		width: 16px;
		height: 16px;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		border-radius: 4px;
		overflow: hidden;
	}

	/* ── Post image thumbnail ── */
	.post-image {
		border-radius: 6px;
		flex-shrink: 0;
	}

	.tt-image {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.play-icon {
		font-size: 0.5rem;
		color: rgba(255, 255, 255, 0.75);
		line-height: 1;
	}

	/* ── Post text content ── */
	.post-body {
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
		padding-right: 0.75rem;
		justify-content: center;
		align-self: center;
	}

	.post-handle {
		font-size: 0.75rem;
		font-weight: 700;
		color: rgba(0, 0, 0, 0.75);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.post-caption {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.45);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.post-views {
		font-size: 0.75rem;
		font-weight: 700;
		color: rgba(255, 255, 255, 0.9);
	}

	.post-views-dark {
		color: rgba(0, 0, 0, 0.75);
	}

	.post-metrics {
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.4);
	}

	/* ── Sponsored pill ── */
	.sponsored-pill {
		display: inline-block;
		font-size: 0.5rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.35);
		background: rgba(0, 0, 0, 0.06);
		border-radius: 999px;
		padding: 0.1rem 0.35rem;
		letter-spacing: 0.02em;
		width: fit-content;
	}
</style>
