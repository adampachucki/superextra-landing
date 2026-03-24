<div class="wrapper">
	<div class="top-bar">
		<svg class="bar-svg" viewBox="0 0 12 12" fill="none">
			<path d="M2,1 H10 Q11,1 11,2 V7 Q11,8 10,8 H5 L2.5,11 V8 H2 Q1,8 1,7 V2 Q1,1 2,1 Z" stroke="rgba(0,0,0,0.3)" stroke-width="1.1"/>
		</svg>
		<span class="bar-label">Review Insights</span>
	</div>

	<div class="topic-strip">
		<span class="topic-header">Trending</span>
		<span class="topic-pill topic-down">speed</span>
		<span class="topic-pill topic-up">cocktails</span>
		<span class="topic-pill topic-down">portions</span>
		<span class="topic-pill topic-up">brunch</span>
	</div>

	<div class="narrative">
		<div class="insight" style="border-left-color: #f472b6;">
			<p class="narrative-text">
				<span class="metric-badge" style="background: rgba(244,114,182,0.1); color: #f472b6;">14% → 23%</span>
				Guest expectations around <strong>speed</strong> tightened considerably over the past year. Mentions of wait time in negative reviews rose from 14% to 23%, even as ticket times held steady — the benchmark moved, not the kitchen.
			</p>
		</div>
		<div class="insight" style="border-left-color: #6366f1;">
			<p class="narrative-text">
				<span class="metric-badge" style="background: rgba(99,102,241,0.1); color: #6366f1;">37% of ★★★★★</span>
				<strong>Cocktail program</strong> emerged as the strongest differentiator, referenced in 37% of 5-star reviews compared to 18% a year ago. Guests treat it as a reason to visit rather than an add-on.
			</p>
		</div>
		<div class="insight" style="border-left-color: #fbbf24;">
			<p class="narrative-text">
				<span class="metric-badge" style="background: rgba(251,191,36,0.1); color: #fbbf24;">+9% pricing</span>
				<strong>Portion perception</strong> softened since mid-2024. The shift correlates with a 9% entrée price increase across the competitive set — not with actual plate changes.
			</p>
		</div>
	</div>

	<div class="footer">
		<span class="footer-sources">847 reviews · Google · Yelp</span>
	</div>
</div>

<style>
	.wrapper {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 115%;
	}

	/* ── Top bar ── */
	.top-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.875rem 1rem;
		border-bottom: 1px solid rgba(0, 0, 0, 0.04);
	}

	.bar-svg {
		width: 13px;
		height: 13px;
	}

	.bar-label {
		font-size: 0.875rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.6);
	}

	/* ── Topic strip ── */
	.topic-strip {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.625rem 1rem;
		border-bottom: 1px solid rgba(0, 0, 0, 0.04);
	}

	.topic-header {
		font-size: 0.5625rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		text-transform: uppercase;
		letter-spacing: 0.03em;
		margin-right: 0.125rem;
	}

	.topic-pill {
		font-size: 0.625rem;
		font-weight: 600;
		padding: 0.25rem 0.5rem;
		border-radius: 0.3rem;
		line-height: 1.3;
	}

	.topic-up {
		background: rgba(34, 197, 94, 0.1);
		color: rgba(22, 163, 74, 0.8);
	}

	.topic-down {
		background: rgba(244, 114, 182, 0.1);
		color: rgba(219, 39, 119, 0.7);
	}

	/* ── Narrative ── */
	.narrative {
		padding: 0.875rem 1rem;
		flex: 1;
		overflow: hidden;
		max-height: 11rem;
		-webkit-mask-image: linear-gradient(to bottom, black 50%, transparent 95%);
		mask-image: linear-gradient(to bottom, black 50%, transparent 95%);
	}

	.insight {
		border-left: 2.5px solid;
		padding-left: 0.75rem;
		margin-bottom: 0.875rem;
	}

	.insight:last-child {
		margin-bottom: 0;
	}

	.metric-badge {
		display: inline-block;
		font-size: 0.625rem;
		font-weight: 600;
		padding: 0.15rem 0.4rem;
		border-radius: 0.25rem;
		margin-right: 0.375rem;
		margin-bottom: 0.15rem;
	}

	.narrative-text {
		font-size: 0.75rem;
		line-height: 1.65;
		color: rgba(0, 0, 0, 0.5);
		margin-bottom: 0;
	}

	.narrative-text :global(strong) {
		font-weight: 600;
		color: rgba(0, 0, 0, 0.75);
	}

	/* ── Footer ── */
	.footer {
		display: flex;
		align-items: center;
		padding: 0.625rem 1rem 0.875rem;
		flex-shrink: 0;
	}

	.footer-sources {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.25);
	}
</style>
