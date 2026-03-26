<div class="wrapper">
	<div class="chat">
		<div class="msg msg-user">
			<p class="bubble bubble-user">How are our entrée prices positioned vs competitors?</p>
		</div>

		<div class="msg msg-ai">
			<p class="bubble bubble-ai">
				Average entrée sits at <strong>€27</strong>, about 12% below the local competitive set. Top performers price <strong>15–20%</strong> higher.
			</p>
		</div>

		<div class="status">
			<svg class="status-sparkle" viewBox="0 0 16 16" fill="none">
				<path d="M8 1.5L9.1 5.9L13.5 7L9.1 8.1L8 12.5L6.9 8.1L2.5 7L6.9 5.9L8 1.5Z" fill="currentColor" />
				<path d="M12.5 1L13 2.5L14.5 3L13 3.5L12.5 5L12 3.5L10.5 3L12 2.5L12.5 1Z" fill="currentColor" />
				<path d="M3.5 10L4 11.5L5.5 12L4 12.5L3.5 14L3 12.5L1.5 12L3 11.5L3.5 10Z" fill="currentColor" />
			</svg>
			<span class="status-text shimmer">Generating charts...</span>
		</div>
	</div>

	<div class="prompt-float">
		<div class="prompt-box prompt-inline">
			<span class="prompt-text">Show cocktail prices vs local avg<span class="cursor"></span></span>
			<div class="prompt-controls">
				<div class="prompt-meta">
					<svg class="meta-icon" viewBox="0 0 16 16" fill="none">
						<path d="M4 6l4-3 4 3M4 10l4 3 4-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
					<span class="meta-label">2</span>
					<svg class="meta-icon" viewBox="0 0 16 16" fill="none">
						<circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.1" />
						<path d="M8 5v3.5l2.5 1.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
					<span class="meta-label">Auto</span>
				</div>
				<div class="prompt-send">
					<svg viewBox="0 0 16 16" fill="none">
						<path d="M8 12V4M8 4L4.5 7.5M8 4L11.5 7.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	.wrapper {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 100%;
	}

	/* ── Chat ── */
	.chat {
		padding: 0 1rem 0.625rem;
		margin-top: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.msg {
		display: flex;
	}

	.msg-user {
		justify-content: flex-end;
		padding-left: 2.5rem;
		margin-right: 0;
	}

	.msg-ai {
		align-items: flex-start;
		gap: 0.5rem;
		margin-right: 1.5rem;
	}

	.avatar {
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 50%;
		background: linear-gradient(135deg, #60a5fa, #38bdf8, #06b6d4);
		flex-shrink: 0;
		margin-top: 0.1rem;
	}

	.bubble {
		font-size: 0.75rem;
		line-height: 1.3;
		padding: 0.75rem 1rem;
		border-radius: 1rem;
	}

	.bubble-user {
		background: rgba(var(--mockup-text), 0.04);
		color: rgba(var(--mockup-text), 0.7);
		border-bottom-right-radius: 0.25rem;
	}

	.bubble-ai {
		background: linear-gradient(135deg, rgba(56, 189, 248, 0.08), rgba(6, 182, 212, 0.06));
		color: rgba(var(--mockup-text), 0.7);
		border-top-left-radius: 0.25rem;
	}

	.bubble strong {
		font-weight: 600;
		color: rgba(var(--mockup-text), 0.85);
	}

	/* ── Status indicator ── */
	.status {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding-left: 1rem;
		margin-top: 0rem;
	}

	.status-sparkle {
		width: 0.75rem;
		height: 0.75rem;
		color: #38bdf8;
		opacity: 0.5;
		flex-shrink: 0;
	}

	.status-text {
		font-size: 0.625rem;
		color: rgba(var(--mockup-text), 0.3);
		font-style: normal;
	}

	.status-text.shimmer {
		color: transparent;
		-webkit-text-fill-color: transparent;
		background: linear-gradient(
			90deg,
			rgba(var(--mockup-text), 0.28) 0%,
			rgba(var(--mockup-text), 0.28) 25%,
			rgba(var(--mockup-text), 0.12) 50%,
			rgba(var(--mockup-text), 0.28) 75%,
			rgba(var(--mockup-text), 0.28) 100%
		);
		-webkit-background-clip: text;
		background-clip: text;
	}

	/* ── Floating prompt ── */
	.prompt-float {
		padding: 0.75rem 1rem 0.5rem 1rem;
	}

	.prompt-box {
		background: rgb(var(--mockup-bg));
		border-radius: 1rem;
		padding: 0.75rem 0.875rem;
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
		box-shadow:
			0 1px 4px rgba(var(--mockup-text), 0.06),
			0 4px 16px rgba(var(--mockup-text), 0.04);
		border: none;
	}

	.prompt-inline {
		gap: 0.375rem;
	}

	.prompt-text {
		font-size: 0.8125rem;
		color: rgba(var(--mockup-text), 0.82);
		line-height: 1.5;
	}

	.cursor {
		display: inline-block;
		width: 1.5px;
		height: 0.875rem;
		background: rgba(var(--mockup-text), 0.7);
		margin-left: 1px;
		vertical-align: text-bottom;
	}

	.prompt-controls {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.prompt-meta {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.meta-icon {
		width: 0.875rem;
		height: 0.875rem;
		color: rgba(var(--mockup-text), 0.2);
	}

	.meta-label {
		font-size: 0.6875rem;
		font-weight: 450;
		color: rgba(var(--mockup-text), 0.22);
		margin-right: 0.375rem;
	}

	.prompt-send {
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		background: rgba(var(--mockup-text), 0.06);
		display: flex;
		align-items: center;
		justify-content: center;
		color: rgba(var(--mockup-text), 0.3);
	}

	.prompt-send svg {
		width: 0.8125rem;
		height: 0.8125rem;
	}

	@media (max-width: 767px) {
		.wrapper {
			min-width: 100%;
		}
		.msg-user {
			padding-left: 3rem;
		}
		.msg-ai {
			margin-right: 0;
		}
		.prompt-float {
			padding-top: 1rem;
		}
	}
</style>
