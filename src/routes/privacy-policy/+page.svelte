<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Seo from '$lib/components/Seo.svelte';
</script>

<Seo
	title="Privacy Policy - Superextra"
	description="Superextra Privacy Policy covering data collection, usage, protection, and retention."
	canonicalPath="/privacy-policy"
	localized={false}
/>

<Navbar />

<article class="mx-auto max-w-[720px] px-6 pt-32 pb-20">
	<h1 class="text-3xl font-medium tracking-tight text-black dark:text-white">Privacy Policy</h1>
	<p class="mt-2 text-sm text-black/40 dark:text-white/40">Last updated: May 30, 2026</p>

	<div
		class="prose prose-sm mt-10 max-w-none text-black/60 prose-neutral dark:text-white/60 dark:prose-invert prose-headings:font-medium prose-headings:text-black dark:prose-headings:text-white prose-h2:mt-10 prose-h2:mb-4 prose-h2:text-lg prose-p:leading-relaxed prose-a:text-black prose-a:underline dark:prose-a:text-white prose-li:leading-relaxed"
	>
		<h2>1. Who we are</h2>
		<p>
			Superextra is operated by <strong>PP2 Studio sp. z o.o.</strong>, a company registered in
			Poland (ul. Żywiczna 9, 81-604 Gdynia; KRS 0001182088; NIP 5862419337). PP2 Studio sp. z o.o.
			is the <strong>data controller</strong> for personal data processed through the Superextra
			website and platform (collectively, the "Service"). Full company details are in our
			<a href="/impressum">Legal Notice</a>.
		</p>
		<p>
			This Privacy Policy explains how we collect, use, disclose, and safeguard personal data when
			you use the Service. We process personal data in accordance with the EU General Data
			Protection Regulation (GDPR) and applicable Polish law. For any privacy question, contact us
			at <a href="mailto:privacy@superextra.ai">privacy@superextra.ai</a>.
		</p>

		<h2>2. Information we collect</h2>
		<h3>Information you provide</h3>
		<ul>
			<li>
				<strong>Account information</strong> — name, email address, company name, and role when you request
				access or create an account.
			</li>
			<li>
				<strong>Communications</strong> — any information you include when you contact us by email or
				through the website.
			</li>
			<li>
				<strong>Payment information</strong> — billing details processed by our payment provider. We do
				not store full payment card numbers.
			</li>
		</ul>

		<h3>Information collected automatically</h3>
		<ul>
			<li>
				<strong>Usage data</strong> — pages viewed, features used, time spent, and interactions within
				the Service.
			</li>
			<li>
				<strong>Device &amp; browser data</strong> — IP address, browser type, operating system, device
				identifiers, and referring URLs.
			</li>
			<li>
				<strong>Cookies &amp; similar technologies</strong> — see Section 7.
			</li>
		</ul>

		<h2>3. How we use your information, and our legal bases</h2>
		<p>Under the GDPR, we rely on the following legal bases (Article 6):</p>
		<ul>
			<li>
				<strong
					>To provide and maintain the Service, manage your account, and process your access request</strong
				> — performance of a contract with you or steps taken at your request before entering a contract
				(Art. 6(1)(b)).
			</li>
			<li>
				<strong>To send transactional emails</strong> (confirmations, security alerts) — performance of
				a contract (Art. 6(1)(b)).
			</li>
			<li>
				<strong
					>To analyse usage, improve features, and keep the Service secure and free of fraud</strong
				>
				— our legitimate interests in operating and improving the Service (Art. 6(1)(f)).
			</li>
			<li>
				<strong>To send marketing communications</strong> — your consent, which you can withdraw at any
				time (Art. 6(1)(a)).
			</li>
			<li>
				<strong>To comply with legal obligations</strong> (e.g. tax and accounting) — compliance with
				a legal obligation (Art. 6(1)(c)).
			</li>
		</ul>

		<h2>4. Chat conversations</h2>
		<p>
			When you use the Superextra chat (research conversations with our AI agent), each chat is
			given a unique URL. A few things about how chats are stored and shared are worth calling out:
		</p>
		<ul>
			<li>
				<strong
					>Every question you ask and every answer you receive is durably stored in the cloud until
					you delete the chat.</strong
				> This includes the sources the agent returned and the activity summary for each turn.
			</li>
			<li>
				<strong>Anyone with the chat URL can read it and continue the conversation.</strong>
				Treat chat URLs like sensitive document links — if the URL is shared, so is the chat.
			</li>
			<li>
				<strong>Only the person who originally created a chat can delete it.</strong> Other people with
				the URL cannot delete your chats.
			</li>
			<li>
				<strong>Anonymous browser identifiers are stored alongside chats.</strong> We record the anonymous
				identifier of the original creator and the anonymous identifiers of every browser that has contributed
				a message to the chat. These are not personally identifying on their own, but they are readable
				by anyone with the chat URL.
			</li>
			<li>
				<strong>Operational activity events</strong> (e.g., per-turn search/tool activity) are retained
				for debugging and reliability, are set to expire after 180 days, and then become eligible for
				automatic deletion. The question, answer, and source list for each turn are retained for as long
				as the chat exists.
			</li>
		</ul>

		<h2>5. How we share your information</h2>
		<p>
			We do not sell your personal data. We share it only with service providers who process it on
			our behalf as processors under a data processing agreement, and only as needed to run the
			Service:
		</p>
		<ul>
			<li><strong>Google Cloud / Vertex AI</strong> — hosting and AI processing of the agent.</li>
			<li><strong>Firebase (Google)</strong> — website hosting, authentication, and database.</li>
			<li><strong>Stripe</strong> — payment processing.</li>
			<li><strong>Resend</strong> — delivery of transactional and intake email.</li>
			<li>
				<strong>ElevenLabs</strong> — speech-to-text and text-to-speech for optional voice features.
			</li>
		</ul>
		<p>
			We may also disclose data where required by law, regulation, or valid legal process, or in
			connection with a merger, acquisition, or sale of assets.
		</p>

		<h2>6. Data retention</h2>
		<p>
			We keep personal data for as long as your account is active or as needed to provide the
			Service. We retain data longer only where necessary to comply with legal obligations (such as
			tax and accounting rules), resolve disputes, and enforce our agreements. When data is no
			longer needed, we securely delete or anonymize it.
		</p>

		<h2>7. Cookies and similar technologies</h2>
		<p>We use:</p>
		<ul>
			<li>
				<strong>Essential cookies and local storage</strong> — required for the Service to function (e.g.,
				authentication, security, and remembering preferences such as your theme and language).
			</li>
			<li>
				<strong>Analytics cookies</strong> — to understand how visitors use the website so we can improve
				it. You can block or delete cookies through your browser settings; disabling essential cookies
				may affect how the Service works.
			</li>
		</ul>

		<h2>8. Data security</h2>
		<p>
			We implement industry-standard technical and organizational measures to protect personal data,
			including encryption in transit (TLS) and at rest and access controls. However, no method of
			transmission or storage is completely secure, and we cannot guarantee absolute security.
		</p>

		<h2>9. International transfers</h2>
		<p>
			Some of our providers process data outside the European Economic Area, including in the United
			States. Where that happens, we rely on appropriate safeguards under the GDPR — primarily the
			European Commission's Standard Contractual Clauses, and adequacy decisions where they apply —
			to protect your data.
		</p>

		<h2>10. Your rights</h2>
		<p>Under the GDPR, you have the right to:</p>
		<ul>
			<li>access the personal data we hold about you;</li>
			<li>request correction of inaccurate data;</li>
			<li>request deletion ("right to be forgotten");</li>
			<li>object to or request restriction of certain processing;</li>
			<li>data portability — receive your data in a structured, machine-readable format;</li>
			<li>withdraw consent at any time, where processing is based on consent.</li>
		</ul>
		<p>
			To exercise these rights, contact us at <a href="mailto:privacy@superextra.ai"
				>privacy@superextra.ai</a
			>. We will respond within one month, as required by the GDPR.
		</p>
		<p>
			You also have the right to lodge a complaint with a supervisory authority. Our lead authority
			is the Polish Personal Data Protection Office (Urząd Ochrony Danych Osobowych), ul. Stanisława
			Moniuszki 1A, 00-014 Warszawa, Poland — and you may also complain to the authority in your
			country of residence.
		</p>

		<h2>11. Children's privacy</h2>
		<p>
			The Service is not directed to individuals under 16. We do not knowingly collect personal data
			from children. If we learn we have collected data from a child, we will delete it promptly.
		</p>

		<h2>12. Changes to this policy</h2>
		<p>
			We may update this Privacy Policy from time to time. We will post the updated policy on this
			page and update the "Last updated" date, and will notify you of material changes. Continued
			use of the Service after changes take effect constitutes acceptance of the revised policy.
		</p>

		<h2>13. Contact us</h2>
		<p>If you have questions about this Privacy Policy, please contact us at:</p>
		<p>
			PP2 Studio sp. z o.o.<br />
			ul. Żywiczna 9, 81-604 Gdynia, Poland<br />
			Email: <a href="mailto:privacy@superextra.ai">privacy@superextra.ai</a>
		</p>
	</div>
</article>

<Footer />
