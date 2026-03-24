<script lang="ts">
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct'];
	const openings = [4, 6, 5, 7, 4, 6, 5, 5, 3, 5];
	const closings = [6, 5, 4, 3, 4, 3, 5, 4, 3, 4];

	const padL = 20;
	const padR = 6;
	const padT = 5;
	const padB = 14;
	const viewW = 260;
	const viewH = 90;
	const plotW = viewW - padL - padR;
	const plotH = viewH - padT - padB;

	const allValues = [...openings, ...closings];
	const minVal = Math.min(...allValues) - 1;
	const maxVal = Math.max(...allValues) + 1;
	const range = maxVal - minVal;

	function toPoints(data: number[]): string {
		return data
			.map((v, i) => {
				const x = padL + (i / (data.length - 1)) * plotW;
				const y = padT + (1 - (v - minVal) / range) * plotH;
				return `${x},${y}`;
			})
			.join(' ');
	}

	const openingsPoints = toPoints(openings);
	const closingsPoints = toPoints(closings);

	const yTicks = [2, 4, 6, 8];
	const xTickIndices = [0, 2, 4, 6, 8];

	const categories = [
		{ name: 'Vegan', openings: 6, closings: 1, grad: 'from-[#6ee7b7] to-[#06b6d4]' },
		{ name: 'Italian', openings: 4, closings: 3, grad: 'from-[#fbbf24] to-[#f472b6]' },
		{ name: 'Asian Fusion', openings: 5, closings: 2, grad: 'from-[#06b6d4] to-[#6366f1]' },
		{ name: 'American', openings: 2, closings: 4, grad: 'from-[#f472b6] to-[#a78bfa]' }
	];
</script>

<div class="report">
	<div class="sidebar">
		<div class="nav-icon active">
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
				<rect x="1" y="1" width="5" height="5" rx="1" fill="currentColor"/>
				<rect x="8" y="1" width="5" height="5" rx="1" fill="currentColor"/>
				<rect x="1" y="8" width="5" height="5" rx="1" fill="currentColor"/>
				<rect x="8" y="8" width="5" height="5" rx="1" fill="currentColor"/>
			</svg>
		</div>
		<div class="nav-icon">
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
				<circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.2"/>
				<path d="M7 4v3.5L9.5 9" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
			</svg>
		</div>
		<div class="nav-icon">
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
				<rect x="1.5" y="2" width="11" height="10" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
				<path d="M1.5 5.5h11" stroke="currentColor" stroke-width="1.2"/>
			</svg>
		</div>
		<div class="nav-icon">
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
				<path d="M2 3.5h10M2 7h10M2 10.5h6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
			</svg>
		</div>
		<div class="nav-spacer"></div>
		<div class="nav-icon">
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
				<circle cx="7" cy="7" r="2" stroke="currentColor" stroke-width="1.2"/>
				<path d="M7 1.5v1.5M7 11v1.5M1.5 7H3M11 7h1.5M3.1 3.1l1.1 1.1M9.8 9.8l1.1 1.1M3.1 10.9l1.1-1.1M9.8 4.2l1.1-1.1" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
			</svg>
		</div>
	</div>

	<div class="content">
		<h2 class="heading">Openings & Closings</h2>

		<p class="narrative">
			Over the trailing twelve months, the Prenzlauer Berg district recorded
			<span class="stat">48 restaurant openings</span>
			against
			<span class="stat decline">38 closings</span>,
			yielding a net gain of ten venues. This marks the third consecutive year of positive net growth in the area, though the pace has moderated compared to the post-pandemic surge of 2023–24.
		</p>

		<div class="chart-activity">
			<div class="activity-col">
				<span class="section-label">ACTIVITY BY CATEGORY</span>
				{#each categories as c}
					<div class="category-row">
						<div class="category-dot bg-gradient-to-br {c.grad}"></div>
						<span class="category-name">{c.name}</span>
						<span class="category-pair">
							<span class="pair-open">+{c.openings}</span>
							<span class="pair-slash">/</span>
							<span class="pair-close">&minus;{c.closings}</span>
						</span>
					</div>
				{/each}
			</div>

			<div class="chart-col">
				<div class="chart-header">
					<span class="section-label">MONTHLY OPENINGS VS CLOSINGS</span>
					<div class="legend">
						<span class="legend-item"><span class="legend-dot" style="background:#6366f1"></span>Open</span>
						<span class="legend-item"><span class="legend-dot" style="background:rgba(var(--mockup-text),0.15)"></span>Close</span>
					</div>
				</div>
				<svg class="line-chart" viewBox="0 0 {viewW} {viewH}">
					<!-- horizontal grid + y-axis labels -->
					{#each yTicks as tick}
						{@const y = padT + (1 - (tick - minVal) / range) * plotH}
						<line x1={padL} y1={y} x2={viewW - padR} y2={y} style="stroke: rgba(var(--mockup-text), 0.05)" stroke-width="0.4" stroke-dasharray="2,2" />
						<text x={padL - 4} y={y + 1.2} text-anchor="end" style="fill: rgba(var(--mockup-text), 0.25)" font-size="3.5">{tick}</text>
					{/each}

					<!-- axes -->
					<line x1={padL} y1={padT} x2={padL} y2={viewH - padB} style="stroke: rgba(var(--mockup-text), 0.08)" stroke-width="0.5" />
					<line x1={padL} y1={viewH - padB} x2={viewW - padR} y2={viewH - padB} style="stroke: rgba(var(--mockup-text), 0.08)" stroke-width="0.5" />

					<!-- x-axis labels -->
					{#each xTickIndices as idx}
						{@const x = padL + (idx / (months.length - 1)) * plotW}
						<text x={x} y={viewH - padB + 7} text-anchor="middle" style="fill: rgba(var(--mockup-text), 0.25)" font-size="3.5">{months[idx]}</text>
					{/each}

					<!-- lines -->
					<polyline
						points={openingsPoints}
						fill="none"
						stroke="#6366f1"
						stroke-width="1"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
					<polyline
						points={closingsPoints}
						fill="none"
						style="stroke: rgba(var(--mockup-text), 0.15)"
						stroke-width="1"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>
			</div>
		</div>
	</div>
</div>

<style>
	.report {
		display: flex;
		flex: 1;
		min-height: 0;
		overflow: hidden;
		transform: scale(1.15);
		transform-origin: top left;
	}

	@media (max-width: 767px) {
		.report {
			transform: scale(1.18);
			min-width: 140%;
		}
	}

	.sidebar {
		width: 2.75rem;
		flex-shrink: 0;
		border-right: 1px solid rgba(var(--mockup-text), 0.06);
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 0.75rem 0;
		gap: 0.25rem;
	}

	.nav-icon {
		width: 2rem;
		height: 2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.375rem;
		color: rgba(var(--mockup-text), 0.25);
		cursor: default;
	}

	.nav-icon.active {
		background: rgba(var(--mockup-text), 0.06);
		color: rgba(var(--mockup-text), 0.55);
	}

	.nav-spacer {
		flex: 1;
	}

	.content {
		flex: 1;
		padding: 1rem 1.5rem;
		overflow: hidden;
		min-width: 0;
	}

	.heading {
		font-size: 0.8125rem;
		font-weight: 600;
		color: rgba(var(--mockup-text), 0.7);
		margin-bottom: 0.5rem;
		font-family: 'Georgia', 'Times New Roman', serif;
	}

	.narrative {
		font-size: 0.75rem;
		line-height: 1.7;
		color: rgba(var(--mockup-text), 0.6);
		margin-bottom: 1.5rem;
		font-family: 'Georgia', 'Times New Roman', serif;
	}

	.stat {
		font-weight: 600;
		color: rgba(var(--mockup-text), 0.85);
		background: rgba(99, 102, 241, 0.06);
		padding: 0.1rem 0.35rem;
		border-radius: 0.2rem;
	}

	.stat.decline {
		background: rgba(244, 114, 182, 0.06);
	}

	/* ── Chart + Activity layout ── */
	.chart-activity {
		display: flex;
		gap: 2rem;
		min-height: 0;
	}

	.chart-col {
		flex: 1;
		min-width: 0;
	}

	.activity-col {
		width: 10rem;
		flex-shrink: 0;
	}

	.section-label {
		font-size: 0.5625rem;
		font-weight: 600;
		letter-spacing: 0.06em;
		color: rgba(var(--mockup-text), 0.3);
		display: block;
		margin-bottom: 0.5rem;
	}

	.chart-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.25rem;
	}

	.legend {
		display: flex;
		gap: 0.5rem;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.2rem;
		font-size: 0.5625rem;
		color: rgba(var(--mockup-text), 0.3);
	}

	.legend-dot {
		width: 0.3125rem;
		height: 0.3125rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.line-chart {
		width: 100%;
		height: auto;
		display: block;
	}

	/* ── Activity rows ── */
	.category-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.3rem 0;
	}

	.category-dot {
		width: 1.25rem;
		height: 1.25rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.category-name {
		flex: 1;
		font-size: 0.6875rem;
		font-weight: 500;
		color: rgba(var(--mockup-text), 0.7);
	}

	.category-pair {
		font-size: 0.625rem;
		display: flex;
		align-items: center;
		gap: 0.15rem;
	}

	.pair-open {
		color: #6366f1;
		font-weight: 600;
	}

	.pair-slash {
		color: rgba(var(--mockup-text), 0.12);
	}

	.pair-close {
		color: rgba(var(--mockup-text), 0.2);
	}
</style>
