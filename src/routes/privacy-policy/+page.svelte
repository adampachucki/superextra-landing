<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import { getLocale, localizeHref } from '$lib/paraglide/runtime';

	const loc = getLocale();

	const seoTitle: Record<string, string> = {
		en: 'Privacy Policy - Superextra',
		de: 'Datenschutzerklärung - Superextra',
		pl: 'Polityka prywatności - Superextra'
	};
	const seoDesc: Record<string, string> = {
		en: 'Superextra Privacy Policy covering data collection, usage, protection, and retention.',
		de: 'Datenschutzerklärung von Superextra zu Erhebung, Nutzung, Schutz und Aufbewahrung von Daten.',
		pl: 'Polityka prywatności Superextra dotycząca gromadzenia, wykorzystywania, ochrony i przechowywania danych.'
	};
	const heading: Record<string, string> = {
		en: 'Privacy Policy',
		de: 'Datenschutzerklärung',
		pl: 'Polityka prywatności'
	};
	const updated: Record<string, string> = {
		en: 'Last updated: May 30, 2026',
		de: 'Zuletzt aktualisiert: 30. Mai 2026',
		pl: 'Ostatnia aktualizacja: 30 maja 2026'
	};
	const imprintLabel: Record<string, string> = {
		en: 'Legal Notice',
		de: 'Impressum',
		pl: 'Dane firmy'
	};
</script>

<Seo title={seoTitle[loc]} description={seoDesc[loc]} canonicalPath="/privacy-policy" />

<Navbar minimal />

<article class="mx-auto max-w-[720px] px-6 pt-32 pb-20">
	<h1 class="text-3xl font-medium tracking-tight text-black dark:text-white">{heading[loc]}</h1>
	<p class="mt-2 text-sm text-black/40 dark:text-white/40">{updated[loc]}</p>

	<div
		class="prose prose-sm mt-10 max-w-none text-black/60 prose-neutral dark:text-white/60 dark:prose-invert prose-headings:font-medium prose-headings:text-black dark:prose-headings:text-white prose-h2:mt-10 prose-h2:mb-4 prose-h2:text-lg prose-p:leading-relaxed prose-a:text-black prose-a:underline dark:prose-a:text-white prose-li:leading-relaxed"
	>
		{#if loc === 'de'}
			<h2>1. Wer wir sind</h2>
			<p>
				Superextra wird betrieben von der <strong>PP2 Studio sp. z o.o.</strong>, einer in Polen
				eingetragenen Gesellschaft (ul. Żywiczna 9, 81-604 Gdynia; KRS 0001182088; NIP 5862419337).
				Die PP2 Studio sp. z o.o. ist <strong>Verantwortlicher</strong> im Sinne der DSGVO für die
				personenbezogenen Daten, die über die Website und Plattform von Superextra (zusammen der
				„Dienst") verarbeitet werden. Vollständige Unternehmensangaben finden Sie in unserem
				<a href={localizeHref('/impressum')}>{imprintLabel[loc]}</a>.
			</p>
			<p>
				Diese Datenschutzerklärung erläutert, wie wir personenbezogene Daten erheben, nutzen,
				offenlegen und schützen, wenn Sie den Dienst nutzen. Wir verarbeiten personenbezogene Daten
				im Einklang mit der Datenschutz-Grundverordnung der EU (DSGVO) und dem geltenden polnischen
				Recht. Bei Datenschutzfragen erreichen Sie uns unter
				<a href="mailto:privacy@superextra.ai">privacy@superextra.ai</a>.
			</p>

			<h2>2. Welche Daten wir erheben</h2>
			<h3>Daten, die Sie bereitstellen</h3>
			<ul>
				<li>
					<strong>Kontodaten</strong> — Name, E-Mail-Adresse, Firmenname und Funktion, wenn Sie Zugang
					anfragen oder ein Konto erstellen.
				</li>
				<li>
					<strong>Kommunikation</strong> — alle Informationen, die Sie angeben, wenn Sie uns per E-Mail
					oder über die Website kontaktieren.
				</li>
				<li>
					<strong>Zahlungsdaten</strong> — Abrechnungsdaten, die von unserem Zahlungsdienstleister verarbeitet
					werden. Vollständige Kartennummern speichern wir nicht.
				</li>
			</ul>

			<h3>Automatisch erhobene Daten</h3>
			<ul>
				<li>
					<strong>Nutzungsdaten</strong> — aufgerufene Seiten, genutzte Funktionen, Verweildauer und Interaktionen
					innerhalb des Dienstes.
				</li>
				<li>
					<strong>Geräte- &amp; Browserdaten</strong> — IP-Adresse, Browsertyp, Betriebssystem, Gerätekennungen
					und Verweis-URLs.
				</li>
				<li><strong>Cookies &amp; ähnliche Technologien</strong> — siehe Abschnitt 7.</li>
			</ul>

			<h2>3. Wie wir Ihre Daten nutzen und unsere Rechtsgrundlagen</h2>
			<p>Nach der DSGVO stützen wir uns auf folgende Rechtsgrundlagen (Artikel 6):</p>
			<ul>
				<li>
					<strong
						>Zur Bereitstellung und Aufrechterhaltung des Dienstes, zur Verwaltung Ihres Kontos und
						zur Bearbeitung Ihrer Zugangsanfrage</strong
					> — Erfüllung eines Vertrags mit Ihnen oder Durchführung vorvertraglicher Maßnahmen auf Ihre
					Anfrage (Art. 6 Abs. 1 lit. b DSGVO).
				</li>
				<li>
					<strong>Zum Versand transaktionsbezogener E-Mails</strong> (Bestätigungen, Sicherheitshinweise)
					— Vertragserfüllung (Art. 6 Abs. 1 lit. b DSGVO).
				</li>
				<li>
					<strong
						>Zur Analyse der Nutzung, zur Verbesserung von Funktionen sowie zur Sicherheit und
						Betrugsprävention</strong
					>
					— unsere berechtigten Interessen am Betrieb und an der Verbesserung des Dienstes (Art. 6 Abs.
					1 lit. f DSGVO).
				</li>
				<li>
					<strong>Zum Versand von Marketingmitteilungen</strong> — Ihre Einwilligung, die Sie jederzeit
					widerrufen können (Art. 6 Abs. 1 lit. a DSGVO).
				</li>
				<li>
					<strong>Zur Erfüllung rechtlicher Verpflichtungen</strong> (z. B. Steuer- und Buchhaltungspflichten)
					— Erfüllung einer rechtlichen Verpflichtung (Art. 6 Abs. 1 lit. c DSGVO).
				</li>
			</ul>

			<h2>4. Chat-Unterhaltungen</h2>
			<p>
				Wenn Sie den Superextra-Chat nutzen (Recherche-Unterhaltungen mit unserem KI-Agenten),
				erhält jeder Chat eine eigene URL. Einige Punkte zur Speicherung und Weitergabe von Chats
				sind hervorzuheben:
			</p>
			<ul>
				<li>
					<strong
						>Jede Frage, die Sie stellen, und jede Antwort, die Sie erhalten, werden dauerhaft in
						der Cloud gespeichert, bis Sie den Chat löschen.</strong
					> Dazu gehören die vom Agenten gelieferten Quellen und die Aktivitätszusammenfassung jeder Runde.
				</li>
				<li>
					<strong>Jede Person mit der Chat-URL kann den Chat lesen und fortsetzen.</strong>
					Behandeln Sie Chat-URLs wie Links zu vertraulichen Dokumenten — wird die URL geteilt, ist es
					auch der Chat.
				</li>
				<li>
					<strong
						>Nur die Person, die einen Chat ursprünglich erstellt hat, kann ihn löschen.</strong
					> Andere Personen mit der URL können Ihre Chats nicht löschen.
				</li>
				<li>
					<strong>Anonyme Browser-Kennungen werden zusammen mit Chats gespeichert.</strong> Wir erfassen
					die anonyme Kennung des ursprünglichen Erstellers sowie die anonymen Kennungen aller Browser,
					die eine Nachricht zum Chat beigetragen haben. Diese sind für sich genommen nicht personenbezogen
					identifizierend, aber für jede Person mit der Chat-URL lesbar.
				</li>
				<li>
					<strong>Betriebsbezogene Aktivitätsereignisse</strong> (z. B. Such-/Tool-Aktivität je Runde)
					werden zur Fehlersuche und Zuverlässigkeit aufbewahrt, laufen nach 180 Tagen ab und werden anschließend
					zur automatischen Löschung freigegeben. Frage, Antwort und Quellenliste jeder Runde werden so
					lange aufbewahrt, wie der Chat besteht.
				</li>
			</ul>

			<h2>5. Weitergabe Ihrer Daten</h2>
			<p>
				Wir verkaufen Ihre personenbezogenen Daten nicht. Wir geben sie nur an Dienstleister weiter,
				die sie in unserem Auftrag als Auftragsverarbeiter auf Grundlage eines
				Auftragsverarbeitungsvertrags verarbeiten, und nur soweit für den Betrieb des Dienstes
				erforderlich:
			</p>
			<ul>
				<li>
					<strong>Google Cloud / Vertex AI</strong> — Hosting und KI-Verarbeitung des Agenten.
				</li>
				<li>
					<strong>Firebase (Google)</strong> — Website-Hosting, Authentifizierung und Datenbank.
				</li>
				<li><strong>Stripe</strong> — Zahlungsabwicklung.</li>
				<li><strong>Resend</strong> — Versand transaktionsbezogener und Intake-E-Mails.</li>
				<li>
					<strong>ElevenLabs</strong> — Sprache-zu-Text und Text-zu-Sprache für optionale Sprachfunktionen.
				</li>
			</ul>
			<p>
				Wir legen Daten zudem offen, soweit dies gesetzlich, behördlich oder durch ein rechtmäßiges
				Verfahren erforderlich ist, oder im Zusammenhang mit einer Fusion, Übernahme oder einem
				Verkauf von Vermögenswerten.
			</p>

			<h2>6. Speicherdauer</h2>
			<p>
				Wir bewahren personenbezogene Daten so lange auf, wie Ihr Konto aktiv ist oder wie es zur
				Erbringung des Dienstes erforderlich ist. Eine längere Aufbewahrung erfolgt nur, soweit dies
				zur Erfüllung rechtlicher Verpflichtungen (etwa steuer- und handelsrechtlicher Vorgaben),
				zur Beilegung von Streitigkeiten und zur Durchsetzung unserer Vereinbarungen erforderlich
				ist. Werden Daten nicht mehr benötigt, löschen oder anonymisieren wir sie sicher.
			</p>

			<h2>7. Cookies und ähnliche Technologien</h2>
			<p>Wir verwenden:</p>
			<ul>
				<li>
					<strong>Essenzielle Cookies und lokalen Speicher</strong> — erforderlich für die Funktion des
					Dienstes (z. B. Authentifizierung, Sicherheit und das Merken von Einstellungen wie Design und
					Sprache).
				</li>
				<li>
					<strong>Analyse-Cookies</strong> — um zu verstehen, wie Besucher die Website nutzen, damit wir
					sie verbessern können. Sie können Cookies über Ihre Browsereinstellungen blockieren oder löschen;
					das Deaktivieren essenzieller Cookies kann die Funktion des Dienstes beeinträchtigen.
				</li>
			</ul>

			<h2>8. Datensicherheit</h2>
			<p>
				Wir treffen branchenübliche technische und organisatorische Maßnahmen zum Schutz
				personenbezogener Daten, einschließlich Verschlüsselung bei der Übertragung (TLS) und im
				Ruhezustand sowie Zugriffskontrollen. Allerdings ist keine Übertragungs- oder
				Speichermethode vollständig sicher, und wir können keine absolute Sicherheit garantieren.
			</p>

			<h2>9. Internationale Datenübermittlungen</h2>
			<p>
				Einige unserer Dienstleister verarbeiten Daten außerhalb des Europäischen Wirtschaftsraums,
				unter anderem in den USA. Soweit dies geschieht, stützen wir uns auf geeignete Garantien
				nach der DSGVO — vor allem die Standardvertragsklauseln der Europäischen Kommission sowie,
				soweit einschlägig, Angemessenheitsbeschlüsse — um Ihre Daten zu schützen.
			</p>

			<h2>10. Ihre Rechte</h2>
			<p>Nach der DSGVO haben Sie das Recht:</p>
			<ul>
				<li>auf Auskunft über die zu Ihnen gespeicherten personenbezogenen Daten;</li>
				<li>auf Berichtigung unrichtiger Daten;</li>
				<li>auf Löschung („Recht auf Vergessenwerden");</li>
				<li>auf Widerspruch gegen bestimmte Verarbeitungen oder auf deren Einschränkung;</li>
				<li>
					auf Datenübertragbarkeit — Erhalt Ihrer Daten in einem strukturierten, maschinenlesbaren
					Format;
				</li>
				<li>
					die Einwilligung jederzeit zu widerrufen, soweit die Verarbeitung auf einer Einwilligung
					beruht.
				</li>
			</ul>
			<p>
				Zur Ausübung dieser Rechte erreichen Sie uns unter <a href="mailto:privacy@superextra.ai"
					>privacy@superextra.ai</a
				>. Wir antworten innerhalb eines Monats, wie von der DSGVO vorgesehen.
			</p>
			<p>
				Ihnen steht zudem ein Beschwerderecht bei einer Aufsichtsbehörde zu. Unsere federführende
				Aufsichtsbehörde ist das polnische Amt für den Schutz personenbezogener Daten (Urząd Ochrony
				Danych Osobowych), ul. Stanisława Moniuszki 1A, 00-014 Warszawa, Polen — Sie können sich
				auch an die Aufsichtsbehörde Ihres Wohnsitzlandes wenden.
			</p>

			<h2>11. Datenschutz von Kindern</h2>
			<p>
				Der Dienst richtet sich nicht an Personen unter 16 Jahren. Wir erheben wissentlich keine
				personenbezogenen Daten von Kindern. Sollten wir feststellen, dass wir Daten eines Kindes
				erhoben haben, löschen wir diese umgehend.
			</p>

			<h2>12. Änderungen dieser Erklärung</h2>
			<p>
				Wir können diese Datenschutzerklärung von Zeit zu Zeit aktualisieren. Wir veröffentlichen
				die aktualisierte Fassung auf dieser Seite, passen das Datum „Zuletzt aktualisiert" an und
				informieren Sie über wesentliche Änderungen. Die fortgesetzte Nutzung des Dienstes nach
				Inkrafttreten der Änderungen gilt als Annahme der geänderten Erklärung.
			</p>

			<h2>13. Kontakt</h2>
			<p>Bei Fragen zu dieser Datenschutzerklärung erreichen Sie uns unter:</p>
			<p>
				PP2 Studio sp. z o.o.<br />
				ul. Żywiczna 9, 81-604 Gdynia, Polen<br />
				E-Mail: <a href="mailto:privacy@superextra.ai">privacy@superextra.ai</a>
			</p>
		{:else if loc === 'pl'}
			<h2>1. Kim jesteśmy</h2>
			<p>
				Superextra jest prowadzone przez <strong>PP2 Studio sp. z o.o.</strong>, spółkę
				zarejestrowaną w Polsce (ul. Żywiczna 9, 81-604 Gdynia; KRS 0001182088; NIP 5862419337). PP2
				Studio sp. z o.o. jest <strong>administratorem danych osobowych</strong> przetwarzanych za
				pośrednictwem strony internetowej i platformy Superextra (łącznie „Usługa"). Pełne dane
				spółki znajdują się w sekcji <a href={localizeHref('/impressum')}>{imprintLabel[loc]}</a>.
			</p>
			<p>
				Niniejsza Polityka prywatności wyjaśnia, w jaki sposób gromadzimy, wykorzystujemy, ujawniamy
				i chronimy dane osobowe podczas korzystania z Usługi. Dane osobowe przetwarzamy zgodnie z
				Ogólnym rozporządzeniem o ochronie danych UE (RODO) oraz obowiązującym prawem polskim. W
				sprawach dotyczących ochrony danych prosimy o kontakt:
				<a href="mailto:privacy@superextra.ai">privacy@superextra.ai</a>.
			</p>

			<h2>2. Jakie dane gromadzimy</h2>
			<h3>Dane, które Państwo podają</h3>
			<ul>
				<li>
					<strong>Dane konta</strong> — imię i nazwisko, adres e-mail, nazwa firmy oraz stanowisko, gdy
					proszą Państwo o dostęp lub tworzą konto.
				</li>
				<li>
					<strong>Korespondencja</strong> — wszelkie informacje przekazane podczas kontaktu z nami pocztą
					elektroniczną lub za pośrednictwem strony.
				</li>
				<li>
					<strong>Dane płatnicze</strong> — dane rozliczeniowe przetwarzane przez naszego dostawcę płatności.
					Nie przechowujemy pełnych numerów kart płatniczych.
				</li>
			</ul>

			<h3>Dane gromadzone automatycznie</h3>
			<ul>
				<li>
					<strong>Dane o korzystaniu</strong> — przeglądane strony, używane funkcje, czas spędzony oraz
					interakcje w ramach Usługi.
				</li>
				<li>
					<strong>Dane urządzenia i przeglądarki</strong> — adres IP, typ przeglądarki, system operacyjny,
					identyfikatory urządzenia oraz odsyłające adresy URL.
				</li>
				<li><strong>Pliki cookie i podobne technologie</strong> — zob. sekcja 7.</li>
			</ul>

			<h2>3. Jak wykorzystujemy Państwa dane i nasze podstawy prawne</h2>
			<p>Zgodnie z RODO opieramy się na następujących podstawach prawnych (art. 6):</p>
			<ul>
				<li>
					<strong
						>W celu świadczenia i utrzymania Usługi, zarządzania kontem oraz obsługi wniosku o
						dostęp</strong
					> — wykonanie umowy z Państwem lub podjęcie działań na Państwa żądanie przed jej zawarciem (art.
					6 ust. 1 lit. b RODO).
				</li>
				<li>
					<strong>W celu wysyłania wiadomości transakcyjnych</strong> (potwierdzenia, powiadomienia bezpieczeństwa)
					— wykonanie umowy (art. 6 ust. 1 lit. b RODO).
				</li>
				<li>
					<strong
						>W celu analizy korzystania, ulepszania funkcji oraz zapewnienia bezpieczeństwa i
						przeciwdziałania nadużyciom</strong
					>
					— nasz prawnie uzasadniony interes w prowadzeniu i ulepszaniu Usługi (art. 6 ust. 1 lit. f RODO).
				</li>
				<li>
					<strong>W celu wysyłania komunikatów marketingowych</strong> — Państwa zgoda, którą mogą Państwo
					wycofać w dowolnym momencie (art. 6 ust. 1 lit. a RODO).
				</li>
				<li>
					<strong>W celu wypełnienia obowiązków prawnych</strong> (np. podatkowych i rachunkowych) — wypełnienie
					obowiązku prawnego (art. 6 ust. 1 lit. c RODO).
				</li>
			</ul>

			<h2>4. Rozmowy w czacie</h2>
			<p>
				Gdy korzystają Państwo z czatu Superextra (rozmowy badawcze z naszym agentem AI), każda
				rozmowa otrzymuje unikalny adres URL. Warto zwrócić uwagę na kilka kwestii dotyczących
				przechowywania i udostępniania rozmów:
			</p>
			<ul>
				<li>
					<strong
						>Każde zadane pytanie i każda otrzymana odpowiedź są trwale przechowywane w chmurze do
						czasu usunięcia rozmowy.</strong
					> Obejmuje to źródła zwrócone przez agenta oraz podsumowanie aktywności dla każdej tury.
				</li>
				<li>
					<strong>Każda osoba posiadająca adres URL rozmowy może ją odczytać i kontynuować.</strong>
					Adresy URL rozmów należy traktować jak linki do poufnych dokumentów — udostępnienie adresu oznacza
					udostępnienie rozmowy.
				</li>
				<li>
					<strong>Tylko osoba, która utworzyła rozmowę, może ją usunąć.</strong> Inne osoby posiadające
					adres URL nie mogą usuwać Państwa rozmów.
				</li>
				<li>
					<strong>Wraz z rozmowami przechowywane są anonimowe identyfikatory przeglądarek.</strong> Zapisujemy
					anonimowy identyfikator twórcy rozmowy oraz anonimowe identyfikatory wszystkich przeglądarek,
					które dodały wiadomość do rozmowy. Same w sobie nie identyfikują osoby, lecz są widoczne dla
					każdego, kto posiada adres URL rozmowy.
				</li>
				<li>
					<strong>Zdarzenia aktywności operacyjnej</strong> (np. aktywność wyszukiwania/narzędzi w danej
					turze) są przechowywane na potrzeby diagnostyki i niezawodności, wygasają po 180 dniach, a następnie
					kwalifikują się do automatycznego usunięcia. Pytanie, odpowiedź i lista źródeł dla każdej tury
					są przechowywane tak długo, jak istnieje rozmowa.
				</li>
			</ul>

			<h2>5. Udostępnianie Państwa danych</h2>
			<p>
				Nie sprzedajemy Państwa danych osobowych. Udostępniamy je wyłącznie usługodawcom, którzy
				przetwarzają je w naszym imieniu jako podmioty przetwarzające na podstawie umowy powierzenia
				przetwarzania, i tylko w zakresie niezbędnym do działania Usługi:
			</p>
			<ul>
				<li><strong>Google Cloud / Vertex AI</strong> — hosting i przetwarzanie AI agenta.</li>
				<li>
					<strong>Firebase (Google)</strong> — hosting strony, uwierzytelnianie i baza danych.
				</li>
				<li><strong>Stripe</strong> — obsługa płatności.</li>
				<li><strong>Resend</strong> — dostarczanie wiadomości transakcyjnych i kontaktowych.</li>
				<li>
					<strong>ElevenLabs</strong> — zamiana mowy na tekst i tekstu na mowę dla opcjonalnych funkcji
					głosowych.
				</li>
			</ul>
			<p>
				Możemy także ujawnić dane, gdy wymaga tego prawo, organ publiczny lub zgodne z prawem
				żądanie prawne, albo w związku z fuzją, przejęciem lub sprzedażą aktywów.
			</p>

			<h2>6. Okres przechowywania</h2>
			<p>
				Przechowujemy dane osobowe tak długo, jak Państwa konto jest aktywne lub jak jest to
				niezbędne do świadczenia Usługi. Dłużej przechowujemy dane wyłącznie wtedy, gdy jest to
				konieczne do wypełnienia obowiązków prawnych (np. przepisów podatkowych i rachunkowych),
				rozstrzygania sporów i egzekwowania naszych umów. Gdy dane nie są już potrzebne, bezpiecznie
				je usuwamy lub anonimizujemy.
			</p>

			<h2>7. Pliki cookie i podobne technologie</h2>
			<p>Stosujemy:</p>
			<ul>
				<li>
					<strong>Niezbędne pliki cookie i pamięć lokalną</strong> — wymagane do działania Usługi (np.
					uwierzytelnianie, bezpieczeństwo oraz zapamiętywanie ustawień, takich jak motyw i język).
				</li>
				<li>
					<strong>Analityczne pliki cookie</strong> — aby zrozumieć, jak odwiedzający korzystają ze strony,
					i móc ją ulepszać. Pliki cookie można blokować lub usuwać w ustawieniach przeglądarki; wyłączenie
					niezbędnych plików cookie może wpłynąć na działanie Usługi.
				</li>
			</ul>

			<h2>8. Bezpieczeństwo danych</h2>
			<p>
				Stosujemy zgodne ze standardami branżowymi środki techniczne i organizacyjne w celu ochrony
				danych osobowych, w tym szyfrowanie podczas przesyłania (TLS) i w spoczynku oraz kontrolę
				dostępu. Żadna metoda przesyłania ani przechowywania nie jest jednak w pełni bezpieczna i
				nie możemy zagwarantować absolutnego bezpieczeństwa.
			</p>

			<h2>9. Przekazywanie danych poza EOG</h2>
			<p>
				Niektórzy z naszych dostawców przetwarzają dane poza Europejskim Obszarem Gospodarczym, w
				tym w Stanach Zjednoczonych. W takich przypadkach stosujemy odpowiednie zabezpieczenia
				wymagane przez RODO — przede wszystkim standardowe klauzule umowne Komisji Europejskiej
				oraz, w stosownych przypadkach, decyzje stwierdzające odpowiedni stopień ochrony — aby
				chronić Państwa dane.
			</p>

			<h2>10. Państwa prawa</h2>
			<p>Zgodnie z RODO przysługuje Państwu prawo do:</p>
			<ul>
				<li>dostępu do danych osobowych, które przechowujemy na Państwa temat;</li>
				<li>żądania sprostowania nieprawidłowych danych;</li>
				<li>żądania usunięcia danych („prawo do bycia zapomnianym");</li>
				<li>wniesienia sprzeciwu wobec określonego przetwarzania lub żądania jego ograniczenia;</li>
				<li>
					przenoszenia danych — otrzymania danych w ustrukturyzowanym, nadającym się do odczytu
					maszynowego formacie;
				</li>
				<li>
					wycofania zgody w dowolnym momencie, jeżeli przetwarzanie odbywa się na podstawie zgody.
				</li>
			</ul>
			<p>
				Aby skorzystać z tych praw, prosimy o kontakt: <a href="mailto:privacy@superextra.ai"
					>privacy@superextra.ai</a
				>. Odpowiemy w ciągu miesiąca, zgodnie z wymogami RODO.
			</p>
			<p>
				Przysługuje Państwu również prawo wniesienia skargi do organu nadzorczego. Naszym wiodącym
				organem nadzorczym jest Prezes Urzędu Ochrony Danych Osobowych, ul. Stanisława Moniuszki 1A,
				00-014 Warszawa — mogą Państwo również wnieść skargę do organu właściwego dla miejsca
				zamieszkania.
			</p>

			<h2>11. Prywatność dzieci</h2>
			<p>
				Usługa nie jest skierowana do osób poniżej 16. roku życia. Nie gromadzimy świadomie danych
				osobowych dzieci. Jeżeli stwierdzimy, że zgromadziliśmy dane dziecka, niezwłocznie je
				usuniemy.
			</p>

			<h2>12. Zmiany niniejszej Polityki</h2>
			<p>
				Możemy okresowo aktualizować niniejszą Politykę prywatności. Zaktualizowaną wersję
				opublikujemy na tej stronie, zaktualizujemy datę „Ostatnia aktualizacja" i poinformujemy o
				istotnych zmianach. Dalsze korzystanie z Usługi po wejściu zmian w życie oznacza akceptację
				zmienionej Polityki.
			</p>

			<h2>13. Kontakt</h2>
			<p>W razie pytań dotyczących niniejszej Polityki prywatności prosimy o kontakt:</p>
			<p>
				PP2 Studio sp. z o.o.<br />
				ul. Żywiczna 9, 81-604 Gdynia, Polska<br />
				E-mail: <a href="mailto:privacy@superextra.ai">privacy@superextra.ai</a>
			</p>
		{:else}
			<h2>1. Who we are</h2>
			<p>
				Superextra is operated by <strong>PP2 Studio sp. z o.o.</strong>, a company registered in
				Poland (ul. Żywiczna 9, 81-604 Gdynia; KRS 0001182088; NIP 5862419337). PP2 Studio sp. z
				o.o. is the <strong>data controller</strong> for personal data processed through the
				Superextra website and platform (collectively, the "Service"). Full company details are in
				our
				<a href={localizeHref('/impressum')}>{imprintLabel[loc]}</a>.
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
					<strong>Account information</strong> — name, email address, company name, and role when you
					request access or create an account.
				</li>
				<li>
					<strong>Communications</strong> — any information you include when you contact us by email or
					through the website.
				</li>
				<li>
					<strong>Payment information</strong> — billing details processed by our payment provider. We
					do not store full payment card numbers.
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
				<li><strong>Cookies &amp; similar technologies</strong> — see Section 7.</li>
			</ul>

			<h2>3. How we use your information, and our legal bases</h2>
			<p>Under the GDPR, we rely on the following legal bases (Article 6):</p>
			<ul>
				<li>
					<strong
						>To provide and maintain the Service, manage your account, and process your access
						request</strong
					> — performance of a contract with you or steps taken at your request before entering a contract
					(Art. 6(1)(b)).
				</li>
				<li>
					<strong>To send transactional emails</strong> (confirmations, security alerts) — performance
					of a contract (Art. 6(1)(b)).
				</li>
				<li>
					<strong
						>To analyse usage, improve features, and keep the Service secure and free of fraud</strong
					>
					— our legitimate interests in operating and improving the Service (Art. 6(1)(f)).
				</li>
				<li>
					<strong>To send marketing communications</strong> — your consent, which you can withdraw at
					any time (Art. 6(1)(a)).
				</li>
				<li>
					<strong>To comply with legal obligations</strong> (e.g. tax and accounting) — compliance with
					a legal obligation (Art. 6(1)(c)).
				</li>
			</ul>

			<h2>4. Chat conversations</h2>
			<p>
				When you use the Superextra chat (research conversations with our AI agent), each chat is
				given a unique URL. A few things about how chats are stored and shared are worth calling
				out:
			</p>
			<ul>
				<li>
					<strong
						>Every question you ask and every answer you receive is durably stored in the cloud
						until you delete the chat.</strong
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
					automatic deletion. The question, answer, and source list for each turn are retained for as
					long as the chat exists.
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
				Service. We retain data longer only where necessary to comply with legal obligations (such
				as tax and accounting rules), resolve disputes, and enforce our agreements. When data is no
				longer needed, we securely delete or anonymize it.
			</p>

			<h2>7. Cookies and similar technologies</h2>
			<p>We use:</p>
			<ul>
				<li>
					<strong>Essential cookies and local storage</strong> — required for the Service to function
					(e.g., authentication, security, and remembering preferences such as your theme and language).
				</li>
				<li>
					<strong>Analytics cookies</strong> — to understand how visitors use the website so we can improve
					it. You can block or delete cookies through your browser settings; disabling essential cookies
					may affect how the Service works.
				</li>
			</ul>

			<h2>8. Data security</h2>
			<p>
				We implement industry-standard technical and organizational measures to protect personal
				data, including encryption in transit (TLS) and at rest and access controls. However, no
				method of transmission or storage is completely secure, and we cannot guarantee absolute
				security.
			</p>

			<h2>9. International transfers</h2>
			<p>
				Some of our providers process data outside the European Economic Area, including in the
				United States. Where that happens, we rely on appropriate safeguards under the GDPR —
				primarily the European Commission's Standard Contractual Clauses, and adequacy decisions
				where they apply — to protect your data.
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
				You also have the right to lodge a complaint with a supervisory authority. Our lead
				authority is the Polish Personal Data Protection Office (Urząd Ochrony Danych Osobowych),
				ul. Stanisława Moniuszki 1A, 00-014 Warszawa, Poland — and you may also complain to the
				authority in your country of residence.
			</p>

			<h2>11. Children's privacy</h2>
			<p>
				The Service is not directed to individuals under 16. We do not knowingly collect personal
				data from children. If we learn we have collected data from a child, we will delete it
				promptly.
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
		{/if}
	</div>
</article>

<Footer />
