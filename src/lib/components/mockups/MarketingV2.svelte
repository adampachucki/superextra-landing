<div class="spread-wrap">
	<!-- Left card: Instagram — partially off-screen left -->
	<div class="post-card card-left">
		<div class="post-header">
			<div class="avatar avatar-ig">
				<svg width="10" height="10" viewBox="0 0 24 24" fill="none">
					<circle cx="12" cy="12" r="5" stroke="white" stroke-width="1.5" fill="none"/>
					<circle cx="17.5" cy="6.5" r="1.5" fill="white"/>
				</svg>
			</div>
			<span class="post-name">@theburgerbar</span>
		</div>
		<div class="post-image" style="background: linear-gradient(135deg, #f59e0b, #ec4899);"></div>
		<div class="post-footer">
			<div class="ig-actions">
				<svg class="action-icon" viewBox="0 0 20 20" fill="none">
					<path d="M10 17S2 12 2 7a4 4 0 018 0 4 4 0 018 0c0 5-8 10-8 10z" fill="#ec4899" opacity="0.85"/>
				</svg>
				<svg class="action-icon" viewBox="0 0 20 20" fill="none">
					<path d="M2 3a1 1 0 011-1h14a1 1 0 011 1v10a1 1 0 01-1 1H6l-4 3V3z" fill="none" stroke="rgba(0,0,0,0.35)" stroke-width="1.5"/>
				</svg>
				<svg class="action-icon" viewBox="0 0 20 20" fill="none">
					<path d="M14 10l-4-5v3H3v4h7v3l4-5z" fill="none" stroke="rgba(0,0,0,0.35)" stroke-width="1.5"/>
				</svg>
			</div>
			<span class="likes-count">2.847 likes</span>
		</div>
	</div>

	<!-- Center card: TikTok — centered, highest -->
	<div class="post-card card-center">
		<div class="post-image post-image-tt" style="background: linear-gradient(180deg, #4f46e5 0%, #a78bfa 100%);">
			<svg class="play-btn" viewBox="0 0 24 24" fill="none">
				<path d="M8 5l13 7-13 7V5z" fill="white" opacity="0.9"/>
			</svg>
			<div class="tt-side">
				<div class="tt-action">
					<svg viewBox="0 0 24 24" fill="white" stroke="none">
						<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
					</svg>
					<span>4,2K</span>
				</div>
				<div class="tt-action">
					<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
						<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
					</svg>
					<span>318</span>
				</div>
				<div class="tt-action">
					<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
						<line x1="22" y1="2" x2="11" y2="13"/>
						<polygon points="22 2 15 22 11 13 2 9 22 2"/>
					</svg>
					<span>89</span>
				</div>
			</div>
			<div class="tt-overlay">
				<span class="tt-handle">@theburgerbar</span>
				<span class="tt-views">14,2K views</span>
			</div>
		</div>
	</div>

	<!-- Right card: Facebook — partially off-screen right -->
	<div class="post-card card-right">
		<div class="post-header">
			<div class="avatar avatar-fb">
				<svg width="12" height="12" viewBox="0 0 24 24" fill="none">
					<path d="M13.5 8H16V5.5h-2.5C11.5 5.5 10 7 10 9v1.5H8V13h2v8h3v-8h2l.5-2.5H13V9c0-.6.2-1 .5-1z" fill="white"/>
				</svg>
			</div>
			<div class="post-meta">
				<span class="post-name">The Burger Bar</span>
				<span class="sponsored-pill">Sponsored</span>
			</div>
		</div>
		<div class="post-image" style="background: linear-gradient(135deg, #06b6d4, #6ee7b7);"></div>
		<div class="post-footer">
			<div class="reaction-row">
				<span class="reaction">👍</span>
				<span class="reaction">❤️</span>
				<span class="reaction-count">342 reactions</span>
			</div>
		</div>
	</div>
</div>

<style>
	.spread-wrap {
		position: relative;
		flex: 1;
		overflow: hidden;
	}

	/* ── Shared card base ── */
	.post-card {
		position: absolute;
		width: 52%;
		border-radius: 0.75rem;
		border: 1px solid rgba(0, 0, 0, 0.06);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}

	/* ── Card positions ── */
	.card-left {
		left: -8%;
		top: 2rem;
		z-index: 1;
		background: #ffffff;
	}

	.card-center {
		left: 50%;
		transform: translateX(-50%);
		top: 0.5rem;
		z-index: 3;
		background: #4f46e5;
	}

	.card-right {
		right: -16%;
		top: 3.5rem;
		z-index: 2;
		background: #ffffff;
	}

	/* ── Post header ── */
	.post-header {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.4rem 0.5rem;
	}

	/* ── Avatars ── */
	.avatar {
		flex-shrink: 0;
		width: 1.25rem;
		height: 1.25rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.avatar-ig {
		background: linear-gradient(135deg, #f59e0b 0%, #ec4899 50%, #8b5cf6 100%);
	}

	.avatar-fb {
		background: #1877f2;
	}

	/* ── Meta ── */
	.post-meta {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.post-name {
		font-size: 0.5625rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.7);
		white-space: nowrap;
	}

	.sponsored-pill {
		font-size: 0.45rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.4);
		background: rgba(0, 0, 0, 0.06);
		border-radius: 0.125rem;
		padding: 0.1em 0.35em;
		white-space: nowrap;
	}

	/* ── Post images ── */
	.post-image {
		width: 100%;
		aspect-ratio: 1 / 1;
		flex-shrink: 0;
	}

	.post-image-tt {
		aspect-ratio: 9 / 14;
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.play-btn {
		width: 1.5rem;
		height: 1.5rem;
		flex-shrink: 0;
		position: relative;
		z-index: 1;
	}

	.tt-side {
		position: absolute;
		right: 0.3125rem;
		bottom: 2rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		align-items: center;
	}

	.tt-action {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.0625rem;
	}

	.tt-action svg {
		width: 0.875rem;
		height: 0.875rem;
		filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.4));
	}

	.tt-action span {
		font-size: 0.4375rem;
		font-weight: 600;
		color: rgba(255, 255, 255, 0.9);
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
	}

	.tt-overlay {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: 0.375rem 0.5rem;
		background: linear-gradient(to top, rgba(0, 0, 0, 0.35) 0%, rgba(0, 0, 0, 0.12) 40%, transparent 100%);
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.tt-handle {
		font-size: 0.5rem;
		font-weight: 600;
		color: rgba(255, 255, 255, 0.9);
	}

	.tt-views {
		font-size: 0.4375rem;
		color: rgba(255, 255, 255, 0.65);
	}

	/* ── Post footer ── */
	.post-footer {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		padding: 0.375rem 0.5rem 0.4rem;
	}

	/* Instagram actions */
	.ig-actions {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.action-icon {
		width: 0.6875rem;
		height: 0.6875rem;
		flex-shrink: 0;
	}

	.likes-count {
		font-size: 0.5rem;
		font-weight: 700;
		color: rgba(0, 0, 0, 0.75);
	}

	/* Facebook footer */
	.reaction-row {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.reaction {
		font-size: 0.5rem;
		line-height: 1;
	}

	.reaction-count {
		font-size: 0.4375rem;
		color: rgba(0, 0, 0, 0.4);
		white-space: nowrap;
	}
</style>
