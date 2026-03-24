<div class="float-wrap">

	<!-- Like button pill -->
	<div class="pill pill-a">
		<svg class="pill-icon" viewBox="0 0 24 24" fill="#ef4444" stroke="#ef4444" stroke-width="2">
			<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
		</svg>
		<span class="pill-text">2.847</span>
	</div>

	<!-- Comment input -->
	<div class="card-float card-b">
		<span class="comment-text">Add a comment…</span>
	</div>

	<!-- Share pill -->
	<div class="pill pill-c">
		<svg class="pill-icon" viewBox="0 0 24 24" fill="none" stroke="rgba(0,0,0,0.5)" stroke-width="2">
			<line x1="22" y1="2" x2="11" y2="13"/>
			<polygon points="22 2 15 22 11 13 2 9 22 2"/>
		</svg>
		<span class="pill-text">Share</span>
	</div>

	<!-- Bookmark -->
	<div class="pill pill-d">
		<svg class="pill-icon" viewBox="0 0 24 24" fill="none" stroke="rgba(0,0,0,0.5)" stroke-width="2">
			<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
		</svg>
		<span class="pill-text">Save</span>
	</div>

	<!-- Follow button -->
	<div class="card-float card-e">
		<span class="follow-text">Follow</span>
		<span class="follow-chevron">›</span>
	</div>

	<!-- Views pill -->
	<div class="pill pill-f">
		<span class="pill-text">14,2K views</span>
	</div>

	<!-- Repost pill -->
	<div class="pill pill-g">
		<svg class="pill-icon" viewBox="0 0 24 24" fill="none" stroke="rgba(0,0,0,0.5)" stroke-width="2">
			<path d="M17 1l4 4-4 4"/>
			<path d="M3 11V9a4 4 0 014-4h14"/>
			<path d="M7 23l-4-4 4-4"/>
			<path d="M21 13v2a4 4 0 01-4 4H3"/>
		</svg>
		<span class="pill-text">Repost</span>
	</div>

</div>

<style>
	.float-wrap {
		position: relative;
		flex: 1;
		overflow: hidden;
	}

	/* ── Shared pill ── */
	.pill {
		position: absolute;
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		background: #fff;
		border-radius: 999px;
		padding: 0.625rem 1.125rem;
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.07);
		white-space: nowrap;
	}

	.pill-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}

	.pill-text {
		font-size: 0.9375rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.6);
	}

	/* ── Shared card ── */
	.card-float {
		position: absolute;
		background: #fff;
		border-radius: 14px;
		padding: 0.625rem 1.125rem;
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.07);
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.comment-text {
		font-size: 0.9375rem;
		color: rgba(0, 0, 0, 0.3);
	}

	.follow-text {
		font-size: 0.9375rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.7);
	}

	.follow-chevron {
		font-size: 1.125rem;
		color: rgba(0, 0, 0, 0.25);
		line-height: 1;
	}

	/* ── Positions ── */
	.pill-a {
		top: 1.5rem;
		left: 15%;
	}

	.card-b {
		top: 8rem;
		left: 20%;
	}

	.pill-c {
		top: 4.5rem;
		right: 12%;
	}

	.pill-d {
		bottom: 4rem;
		right: 18%;
	}

	.card-e {
		top: 4rem;
		left: 25%;
	}

	.pill-f {
		top: 1rem;
		right: 15%;
	}

	.pill-g {
		bottom: 3rem;
		left: 30%;
	}
</style>
