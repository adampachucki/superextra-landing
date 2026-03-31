<div class="wrapper">
	<div class="chat">
		<div class="msg msg-user">
			<p class="bubble bubble-user">How is revenue trending this quarter?</p>
		</div>

		<div class="msg msg-ai">
			<div class="avatar"></div>
			<p class="bubble bubble-ai">
				Monthly revenue averaging <strong>€142K</strong>, with consistent 12% year-over-year growth.
				Delivery channel growing at <strong>18%</strong>, now accounting for 28% of total revenue.
			</p>
		</div>

		<div class="status">
			<span class="status-dot"></span>
			<span class="status-text">Generating charts...</span>
		</div>
	</div>

	<div class="prompt-float">
		<div class="prompt-box">
			<span class="prompt-text"
				>Break down delivery revenue by weekday<span class="cursor"></span></span
			>
			<div class="prompt-controls">
				<div class="prompt-meta">
					<svg class="meta-icon" viewBox="0 0 16 16" fill="none">
						<path
							d="M4 6l4-3 4 3M4 10l4 3 4-3"
							stroke="currentColor"
							stroke-width="1.2"
							stroke-linecap="round"
							stroke-linejoin="round"
						/>
					</svg>
					<span class="meta-label">2</span>
					<svg class="meta-icon" viewBox="0 0 16 16" fill="none">
						<circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.1" />
						<path
							d="M8 5v3.5l2.5 1.5"
							stroke="currentColor"
							stroke-width="1.1"
							stroke-linecap="round"
							stroke-linejoin="round"
						/>
					</svg>
					<span class="meta-label">Auto</span>
				</div>
				<div class="prompt-send">
					<svg viewBox="0 0 16 16" fill="none">
						<path
							d="M8 12V4M8 4L4.5 7.5M8 4L11.5 7.5"
							stroke="currentColor"
							stroke-width="1.5"
							stroke-linecap="round"
							stroke-linejoin="round"
						/>
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
		min-width: 115%;
	}

	/* ── Chat ── */
	.chat {
		padding: 1.125rem 1rem 0.625rem;
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.msg {
		display: flex;
	}

	.msg-user {
		justify-content: flex-end;
		padding-left: 1.5rem;
	}

	.msg-ai {
		align-items: flex-start;
		gap: 0.5rem;
		padding-right: 0;
	}

	.avatar {
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 50%;
		background: linear-gradient(135deg, #6366f1, #06b6d4);
		flex-shrink: 0;
		margin-top: 0.1rem;
	}

	.bubble {
		font-size: 0.75rem;
		line-height: 1.5;
		padding: 0.5rem 0.75rem;
		border-radius: 1rem;
	}

	.bubble-user {
		background: rgba(var(--mockup-text), 0.04);
		color: rgba(var(--mockup-text), 0.7);
		border-bottom-right-radius: 0.25rem;
	}

	.bubble-ai {
		background: linear-gradient(135deg, rgba(99, 102, 241, 0.07), rgba(6, 182, 212, 0.06));
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
		padding-left: 2.25rem;
	}

	.status-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: #6366f1;
		opacity: 0.5;
		opacity: 0.5;
	}

	.status-text {
		font-size: 0.625rem;
		color: rgba(var(--mockup-text), 0.3);
		font-style: italic;
	}

	/* ── Floating prompt ── */
	.prompt-float {
		padding: 0.25rem 0.375rem 0.5rem 1.25rem;
	}

	.prompt-box {
		background: rgb(var(--mockup-bg));
		border-radius: 1rem;
		padding: 0.75rem 0.875rem 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
		box-shadow:
			0 1px 3px rgba(var(--mockup-text), 0.06),
			0 4px 12px rgba(var(--mockup-text), 0.04);
		border: 1px solid rgba(var(--mockup-text), 0.04);
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
</style>
