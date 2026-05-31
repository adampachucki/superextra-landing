<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import { getLocale, localizeHref } from '$lib/paraglide/runtime';

	const loc = getLocale();

	const seoTitle: Record<string, string> = {
		en: 'Terms & Conditions - Superextra',
		de: 'Allgemeine Geschäftsbedingungen - Superextra',
		pl: 'Regulamin - Superextra'
	};
	const seoDesc: Record<string, string> = {
		en: 'Superextra Terms & Conditions governing access to and use of the platform.',
		de: 'Allgemeine Geschäftsbedingungen von Superextra für den Zugang zur Plattform und ihre Nutzung.',
		pl: 'Regulamin Superextra określający zasady dostępu do platformy i korzystania z niej.'
	};
	const heading: Record<string, string> = {
		en: 'Terms & Conditions',
		de: 'Allgemeine Geschäftsbedingungen',
		pl: 'Regulamin'
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

<Seo title={seoTitle[loc]} description={seoDesc[loc]} canonicalPath="/terms" />

<Navbar minimal />

<article class="mx-auto max-w-[720px] px-6 pt-32 pb-20">
	<h1 class="text-3xl font-medium tracking-tight text-black dark:text-white">{heading[loc]}</h1>
	<p class="mt-2 text-sm text-black/40 dark:text-white/40">{updated[loc]}</p>

	<div
		class="prose prose-sm mt-10 max-w-none text-black/60 prose-neutral dark:text-white/60 dark:prose-invert prose-headings:font-medium prose-headings:text-black dark:prose-headings:text-white prose-h2:mt-10 prose-h2:mb-4 prose-h2:text-lg prose-p:leading-relaxed prose-a:text-black prose-a:underline dark:prose-a:text-white prose-li:leading-relaxed"
	>
		{#if loc === 'de'}
			<h2>1. Geltung der Bedingungen</h2>
			<p>
				Diese Allgemeinen Geschäftsbedingungen („AGB") regeln den Zugang zur Website und Plattform
				von Superextra (zusammen der „Dienst") sowie deren Nutzung. Der Dienst wird betrieben von
				der
				<strong>PP2 Studio sp. z o.o.</strong>, einer in Polen eingetragenen Gesellschaft (ul.
				Żywiczna 9, 81-604 Gdynia; KRS 0001182088; „wir", „uns" oder „unser"). Vollständige
				Unternehmensangaben finden Sie in unserem
				<a href={localizeHref('/impressum')}>{imprintLabel[loc]}</a>.
			</p>
			<p>
				Mit dem Zugriff auf den Dienst oder seiner Nutzung erklären Sie sich mit diesen AGB
				einverstanden. Wenn Sie nicht einverstanden sind, dürfen Sie den Dienst nicht nutzen.
			</p>

			<h2>2. Ausschließlich geschäftliche Nutzung</h2>
			<p>
				Der Dienst richtet sich an Unternehmen und an Personen, die ihn in deren Namen nutzen. Mit
				der Nutzung des Dienstes bestätigen Sie, dass Sie in geschäftlicher oder beruflicher
				Eigenschaft (als Unternehmer) und nicht als Verbraucher handeln. Sie müssen mindestens 18
				Jahre alt und geschäftsfähig sein, um einen verbindlichen Vertrag zu schließen. Wenn Sie den
				Dienst im Namen eines Unternehmens oder einer Organisation nutzen, sichern Sie zu, dass Sie
				berechtigt sind, dieses Unternehmen an diese AGB zu binden.
			</p>

			<h2>3. Zugang</h2>
			<p>
				Einige Funktionen können einen browserbasierten anonymen Zugang oder einen kontobasierten
				Zugang nutzen, sofern aktiviert. Sie verpflichten sich:
			</p>
			<ul>
				<li>bei Aufforderung richtige, aktuelle und vollständige Angaben zu machen;</li>
				<li>die Sicherheit und Vertraulichkeit der Ihnen erteilten Zugangsdaten zu wahren;</li>
				<li>uns unverzüglich über jede unbefugte Nutzung Ihres Zugangs zu informieren;</li>
				<li>
					die Verantwortung für die über Ihre Browser-Sitzung oder Ihr Konto übermittelten
					Aktivitäten zu übernehmen.
				</li>
			</ul>
			<p>
				Wir behalten uns das Recht vor, einen Zugang zu sperren oder zu beenden, der gegen diese AGB
				verstößt.
			</p>

			<h2>4. Nutzung des Dienstes</h2>
			<p>
				Sie verpflichten sich, den Dienst nur für rechtmäßige Zwecke und im Einklang mit diesen AGB
				zu nutzen. Sie verpflichten sich, nicht:
			</p>
			<ul>
				<li>
					den Dienst in einer Weise zu nutzen, die gegen geltende Gesetze oder Vorschriften
					verstößt;
				</li>
				<li>
					sich unbefugten Zugang zu Teilen des Dienstes, zu anderen Konten oder Systemen zu
					verschaffen;
				</li>
				<li>
					automatisierte Mittel (Bots, Scraper, Crawler) zu verwenden, um ohne unsere vorherige
					schriftliche Zustimmung auf Daten des Dienstes zuzugreifen oder diese zu erheben;
				</li>
				<li>die Integrität oder Leistung des Dienstes zu beeinträchtigen oder zu stören;</li>
				<li>den Dienst zurückzuentwickeln, zu dekompilieren oder zu disassemblieren;</li>
				<li>
					den Zugang zum Dienst oder darüber erlangte Daten ohne unsere vorherige schriftliche
					Zustimmung weiterzuverkaufen, weiterzuverbreiten oder unterzulizenzieren.
				</li>
			</ul>

			<h2>5. Geistiges Eigentum</h2>
			<p>
				Der Dienst sowie seine eigenen Inhalte, Funktionen, Funktionalität und Gestaltung sind
				Eigentum der PP2 Studio sp. z o.o. und durch Urheber-, Marken- und sonstige Rechte des
				geistigen Eigentums geschützt. Unsere Marken und unser Markenauftritt dürfen ohne unsere
				vorherige schriftliche Zustimmung nicht verwendet werden.
			</p>
			<p>
				Sie behalten das Eigentum an allen Daten, die Sie in den Dienst hochladen. Mit dem Hochladen
				von Daten räumen Sie uns ein beschränktes, nicht ausschließliches Recht ein, diese
				ausschließlich zur Erbringung des Dienstes für Sie zu verarbeiten.
			</p>

			<h2>6. Daten &amp; Analysen</h2>
			<p>
				Der Dienst stellt Marktintelligenz, Analysen und Benchmark-Daten für die Gastronomiebranche
				bereit. Wir bemühen uns um Richtigkeit, alle Daten und Erkenntnisse werden jedoch „wie
				besehen" bereitgestellt. Sie erkennen an, dass:
			</p>
			<ul>
				<li>Daten aus Drittquellen und öffentlich zugänglichen Informationen stammen können;</li>
				<li>
					Analysen und Benchmarks Schätzungen sind und nicht die alleinige Grundlage geschäftlicher
					Entscheidungen sein sollten;
				</li>
				<li>
					wir die Richtigkeit, Vollständigkeit oder Aktualität der bereitgestellten Daten nicht
					garantieren.
				</li>
			</ul>

			<h2>7. Entgelte &amp; Zahlung</h2>
			<p>
				Der Zugang zu bestimmten Funktionen des Dienstes kann die Zahlung von Entgelten erfordern.
				Sofern zutreffend:
			</p>
			<ul>
				<li>
					richten sich die Entgelte nach unserer Preisseite oder Ihrer Abonnementvereinbarung;
				</li>
				<li>
					werden alle Entgelte, sofern nicht anders angegeben, in EUR ausgewiesen und verstehen sich
					zuzüglich etwaiger anwendbarer Steuern (etwa USt.), die gegebenenfalls hinzukommen;
				</li>
				<li>behalten wir uns vor, Entgelte mit einer Frist von 30 Tagen zu ändern;</li>
				<li>kann ausbleibende Zahlung zur Sperrung oder Beendigung des Zugangs führen.</li>
			</ul>

			<h2>8. Beendigung</h2>
			<p>
				Wir können Ihren Zugang zum Dienst jederzeit, mit oder ohne Grund, mit oder ohne
				Vorankündigung sperren oder beenden. Bei Beendigung:
			</p>
			<ul>
				<li>endet Ihr Recht zur Nutzung des Dienstes sofort;</li>
				<li>
					können wir Ihr Konto und die zugehörigen Daten nach einer angemessenen Aufbewahrungsfrist
					löschen;
				</li>
				<li>
					bleiben Bestimmungen, die ihrer Natur nach die Beendigung überdauern sollen
					(einschließlich geistiges Eigentum, Haftungsbeschränkung und anwendbares Recht), wirksam.
				</li>
			</ul>
			<p>
				Sie können Ihr Konto jederzeit beenden, indem Sie uns unter <a
					href="mailto:hello@superextra.ai">hello@superextra.ai</a
				> kontaktieren.
			</p>

			<h2>9. Gewährleistungsausschluss</h2>
			<p>
				Soweit gesetzlich zulässig, wird der Dienst „wie besehen" und „wie verfügbar" ohne jegliche
				ausdrückliche oder stillschweigende Gewährleistung bereitgestellt, einschließlich
				stillschweigender Gewährleistungen der Marktgängigkeit, der Eignung für einen bestimmten
				Zweck und der Nichtverletzung von Rechten. Wir gewährleisten nicht, dass der Dienst
				ununterbrochen, sicher oder fehlerfrei ist.
			</p>

			<h2>10. Haftungsbeschränkung</h2>
			<p>
				Soweit gesetzlich zulässig, haftet die PP2 Studio sp. z o.o. nicht für mittelbare,
				beiläufige, besondere oder Folgeschäden oder für entgangenen Gewinn, Umsatz, Daten, Nutzung
				oder Geschäftswert, die sich aus Ihrer Nutzung oder Nichtnutzbarkeit des Dienstes ergeben.
				Unsere Gesamthaftung für einen Anspruch übersteigt nicht den Betrag, den Sie uns in den
				zwölf (12) Monaten vor dem schadensbegründenden Ereignis gezahlt haben.
			</p>
			<p>
				Diese AGB schließen unsere Haftung nicht aus und beschränken sie nicht, soweit sie nach
				geltendem Recht nicht ausgeschlossen oder beschränkt werden kann, einschließlich der Haftung
				für vorsätzlich verursachte Schäden.
			</p>

			<h2>11. Freistellung</h2>
			<p>
				Sie verpflichten sich, die PP2 Studio sp. z o.o. sowie ihre Organe, Geschäftsführer,
				Mitarbeiter und Beauftragten von allen Ansprüchen, Schäden, Verlusten, Verbindlichkeiten und
				Kosten (einschließlich angemessener Rechtsverfolgungskosten) freizustellen, die sich aus
				Ihrer Nutzung des Dienstes oder Ihrem Verstoß gegen diese AGB ergeben.
			</p>

			<h2>12. Anwendbares Recht &amp; Gerichtsstand</h2>
			<p>
				Diese AGB unterliegen dem Recht der Republik Polen und werden nach diesem ausgelegt, ohne
				Rücksicht auf kollisionsrechtliche Grundsätze. Streitigkeiten aus diesen AGB oder dem
				Dienst, die nicht gütlich beigelegt werden können, unterliegen der ausschließlichen
				Zuständigkeit der für den Sitz der PP2 Studio sp. z o.o. zuständigen polnischen Gerichte.
			</p>

			<h2>13. Änderungen dieser AGB</h2>
			<p>
				Wir können diese AGB jederzeit ändern, indem wir die aktualisierte Fassung auf dieser Seite
				veröffentlichen und das Datum „Zuletzt aktualisiert" anpassen. Über wesentliche Änderungen
				informieren wir per E-Mail oder durch einen Hinweis im Dienst. Die fortgesetzte Nutzung des
				Dienstes nach Inkrafttreten der Änderungen gilt als Annahme der geänderten AGB.
			</p>

			<h2>14. Salvatorische Klausel</h2>
			<p>
				Sollte eine Bestimmung dieser AGB unwirksam oder undurchsetzbar sein, bleiben die übrigen
				Bestimmungen in vollem Umfang wirksam.
			</p>

			<h2>15. Kontakt</h2>
			<p>Bei Fragen zu diesen AGB erreichen Sie uns unter:</p>
			<p>
				PP2 Studio sp. z o.o.<br />
				ul. Żywiczna 9, 81-604 Gdynia, Polen<br />
				E-Mail: <a href="mailto:hello@superextra.ai">hello@superextra.ai</a>
			</p>
		{:else if loc === 'pl'}
			<h2>1. Akceptacja Regulaminu</h2>
			<p>
				Niniejszy Regulamin („Regulamin") określa zasady dostępu do strony internetowej i platformy
				Superextra (łącznie „Usługa") oraz korzystania z nich. Usługę prowadzi
				<strong>PP2 Studio sp. z o.o.</strong>, spółka zarejestrowana w Polsce (ul. Żywiczna 9,
				81-604 Gdynia; KRS 0001182088; „my", „nas", „nasze"). Pełne dane spółki znajdują się w
				sekcji
				<a href={localizeHref('/impressum')}>{imprintLabel[loc]}</a>.
			</p>
			<p>
				Uzyskując dostęp do Usługi lub korzystając z niej, akceptują Państwo niniejszy Regulamin. W
				razie braku akceptacji nie mogą Państwo korzystać z Usługi.
			</p>

			<h2>2. Korzystanie wyłącznie w celach biznesowych</h2>
			<p>
				Usługa jest przeznaczona dla przedsiębiorców oraz osób korzystających z niej w ich imieniu.
				Korzystając z Usługi, potwierdzają Państwo, że działają w charakterze biznesowym lub
				zawodowym (jako przedsiębiorca), a nie jako konsument. Muszą Państwo mieć ukończone 18 lat
				oraz zdolność do zawarcia wiążącej umowy. Korzystając z Usługi w imieniu firmy lub
				organizacji, oświadczają Państwo, że są upoważnieni do związania tego podmiotu niniejszym
				Regulaminem.
			</p>

			<h2>3. Dostęp</h2>
			<p>
				Niektóre funkcje mogą wykorzystywać anonimowy dostęp przez przeglądarkę lub dostęp oparty na
				koncie, jeżeli został włączony. Zobowiązują się Państwo do:
			</p>
			<ul>
				<li>podawania dokładnych, aktualnych i kompletnych informacji na żądanie;</li>
				<li>zachowania bezpieczeństwa i poufności wszelkich przyznanych danych dostępowych;</li>
				<li>niezwłocznego powiadamiania nas o nieautoryzowanym użyciu dostępu;</li>
				<li>
					przyjęcia odpowiedzialności za działania podejmowane w ramach sesji przeglądarki lub
					konta.
				</li>
			</ul>
			<p>
				Zastrzegamy sobie prawo do zawieszenia lub zakończenia dostępu naruszającego niniejszy
				Regulamin.
			</p>

			<h2>4. Korzystanie z Usługi</h2>
			<p>
				Zobowiązują się Państwo korzystać z Usługi wyłącznie w celach zgodnych z prawem i z
				niniejszym Regulaminem. Zobowiązują się Państwo nie:
			</p>
			<ul>
				<li>korzystać z Usługi w sposób naruszający obowiązujące przepisy prawa;</li>
				<li>
					podejmować prób nieautoryzowanego dostępu do jakiejkolwiek części Usługi, innych kont lub
					systemów;
				</li>
				<li>
					używać zautomatyzowanych środków (botów, scraperów, crawlerów) w celu dostępu do danych
					Usługi lub ich pozyskiwania bez naszej uprzedniej pisemnej zgody;
				</li>
				<li>zakłócać integralności lub wydajności Usługi;</li>
				<li>
					dokonywać inżynierii wstecznej, dekompilacji ani dezasemblacji jakiegokolwiek elementu
					Usługi;
				</li>
				<li>
					odsprzedawać, rozpowszechniać ani sublicencjonować dostępu do Usługi lub danych uzyskanych
					za jej pośrednictwem bez naszej uprzedniej pisemnej zgody.
				</li>
			</ul>

			<h2>5. Własność intelektualna</h2>
			<p>
				Usługa oraz jej własne treści, funkcje, funkcjonalność i wygląd stanowią własność PP2 Studio
				sp. z o.o. i są chronione prawem autorskim, prawem znaków towarowych oraz innymi przepisami
				o własności intelektualnej. Nasze znaki towarowe i identyfikacja wizualna nie mogą być
				wykorzystywane bez naszej uprzedniej pisemnej zgody.
			</p>
			<p>
				Zachowują Państwo własność wszelkich danych przesłanych do Usługi. Przesyłając dane,
				udzielają Państwo nam ograniczonej, niewyłącznej licencji na ich przetwarzanie wyłącznie w
				celu świadczenia Usługi.
			</p>

			<h2>6. Dane i analizy</h2>
			<p>
				Usługa dostarcza analizy rynkowe oraz dane analityczne i porównawcze dla branży
				gastronomicznej. Dokładamy starań o ich dokładność, jednak wszystkie dane i wnioski
				udostępniane są „w stanie, w jakim się znajdują". Przyjmują Państwo do wiadomości, że:
			</p>
			<ul>
				<li>dane mogą pochodzić ze źródeł zewnętrznych i z powszechnie dostępnych informacji;</li>
				<li>
					analizy i wskaźniki porównawcze stanowią szacunki i nie powinny być jedyną podstawą
					decyzji biznesowych;
				</li>
				<li>nie gwarantujemy dokładności, kompletności ani aktualności udostępnianych danych.</li>
			</ul>

			<h2>7. Opłaty i płatności</h2>
			<p>
				Dostęp do niektórych funkcji Usługi może wymagać uiszczenia opłat. W stosownych przypadkach:
			</p>
			<ul>
				<li>opłaty określone są na naszej stronie z cennikiem lub w umowie subskrypcyjnej;</li>
				<li>
					wszystkie opłaty, o ile nie wskazano inaczej, podawane są w EUR i nie zawierają należnych
					podatków (takich jak VAT), które zostaną doliczone w wymaganym zakresie;
				</li>
				<li>zastrzegamy sobie prawo do zmiany opłat z 30-dniowym wyprzedzeniem;</li>
				<li>brak płatności może skutkować zawieszeniem lub zakończeniem dostępu.</li>
			</ul>

			<h2>8. Zakończenie</h2>
			<p>
				Możemy zawiesić lub zakończyć Państwa dostęp do Usługi w dowolnym momencie, z przyczyną lub
				bez przyczyny, z powiadomieniem lub bez. Z chwilą zakończenia:
			</p>
			<ul>
				<li>Państwa prawo do korzystania z Usługi wygasa natychmiast;</li>
				<li>
					możemy usunąć Państwa konto i powiązane dane po upływie rozsądnego okresu przechowywania;
				</li>
				<li>
					postanowienia, które ze swej natury powinny obowiązywać po zakończeniu (w tym dotyczące
					własności intelektualnej, ograniczenia odpowiedzialności i prawa właściwego), pozostają w
					mocy.
				</li>
			</ul>
			<p>
				Mogą Państwo zakończyć konto w dowolnym momencie, kontaktując się z nami pod adresem <a
					href="mailto:hello@superextra.ai">hello@superextra.ai</a
				>.
			</p>

			<h2>9. Wyłączenie gwarancji</h2>
			<p>
				W najszerszym zakresie dozwolonym przez prawo Usługa udostępniana jest „w stanie, w jakim
				się znajduje" oraz „w miarę dostępności", bez jakichkolwiek gwarancji, wyraźnych ani
				dorozumianych, w tym dorozumianych gwarancji przydatności handlowej, przydatności do
				określonego celu oraz nienaruszania praw. Nie gwarantujemy, że Usługa będzie działać
				nieprzerwanie, bezpiecznie ani bezbłędnie.
			</p>

			<h2>10. Ograniczenie odpowiedzialności</h2>
			<p>
				W najszerszym zakresie dozwolonym przez prawo PP2 Studio sp. z o.o. nie ponosi
				odpowiedzialności za szkody pośrednie, uboczne, szczególne ani następcze, ani za utratę
				zysków, przychodów, danych, możliwości korzystania czy renomy, wynikające z korzystania lub
				niemożności korzystania z Usługi. Nasza łączna odpowiedzialność z tytułu jakiegokolwiek
				roszczenia nie przekroczy kwoty zapłaconej nam w okresie dwunastu (12) miesięcy
				poprzedzających zdarzenie będące podstawą roszczenia.
			</p>
			<p>
				Żadne z postanowień niniejszego Regulaminu nie wyłącza ani nie ogranicza naszej
				odpowiedzialności w zakresie, w jakim nie może ona zostać wyłączona lub ograniczona na mocy
				obowiązującego prawa, w tym odpowiedzialności za szkodę wyrządzoną umyślnie.
			</p>

			<h2>11. Zwolnienie z odpowiedzialności</h2>
			<p>
				Zobowiązują się Państwo zwolnić PP2 Studio sp. z o.o. oraz członków jej organów, kadrę
				zarządzającą, pracowników i przedstawicieli z odpowiedzialności za wszelkie roszczenia,
				szkody, straty, zobowiązania i koszty (w tym uzasadnione koszty obsługi prawnej) wynikające
				z korzystania przez Państwa z Usługi lub z naruszenia niniejszego Regulaminu.
			</p>

			<h2>12. Prawo właściwe i jurysdykcja</h2>
			<p>
				Niniejszy Regulamin podlega prawu polskiemu i zgodnie z nim jest interpretowany, z
				wyłączeniem norm kolizyjnych. Wszelkie spory wynikające z niniejszego Regulaminu lub Usługi,
				których nie uda się rozwiązać polubownie, podlegają wyłącznej jurysdykcji sądów polskich
				właściwych dla siedziby PP2 Studio sp. z o.o.
			</p>

			<h2>13. Zmiany Regulaminu</h2>
			<p>
				Możemy zmieniać niniejszy Regulamin w dowolnym czasie, publikując zaktualizowaną wersję na
				tej stronie i aktualizując datę „Ostatnia aktualizacja". O istotnych zmianach poinformujemy
				pocztą elektroniczną lub poprzez komunikat w Usłudze. Dalsze korzystanie z Usługi po wejściu
				zmian w życie oznacza akceptację zmienionego Regulaminu.
			</p>

			<h2>14. Klauzula salwatoryjna</h2>
			<p>
				Jeżeli którekolwiek postanowienie niniejszego Regulaminu zostanie uznane za nieważne lub
				niewykonalne, pozostałe postanowienia zachowują pełną moc.
			</p>

			<h2>15. Kontakt</h2>
			<p>W razie pytań dotyczących niniejszego Regulaminu prosimy o kontakt:</p>
			<p>
				PP2 Studio sp. z o.o.<br />
				ul. Żywiczna 9, 81-604 Gdynia, Polska<br />
				E-mail: <a href="mailto:hello@superextra.ai">hello@superextra.ai</a>
			</p>
		{:else}
			<h2>1. Agreement to Terms</h2>
			<p>
				These Terms &amp; Conditions ("Terms") govern access to and use of the Superextra website
				and platform (collectively, the "Service"), operated by
				<strong>PP2 Studio sp. z o.o.</strong>, a company registered in Poland (ul. Żywiczna 9,
				81-604 Gdynia; KRS 0001182088; "we", "our", or "us"). Full company details are in our
				<a href={localizeHref('/impressum')}>{imprintLabel[loc]}</a>.
			</p>
			<p>
				By accessing or using the Service, you agree to be bound by these Terms. If you do not
				agree, you may not use the Service.
			</p>

			<h2>2. Business use only</h2>
			<p>
				The Service is intended for businesses and for the people who use it on their behalf. By
				using the Service, you confirm that you are acting in a business or professional capacity
				(as an entrepreneur), and not as a consumer. You must be at least 18 years old and have the
				legal capacity to enter into a binding agreement. If you use the Service on behalf of a
				company or organization, you represent that you have authority to bind that entity to these
				Terms.
			</p>

			<h2>3. Access</h2>
			<p>
				Some features may use browser-based anonymous access or account-based access if enabled. You
				agree to:
			</p>
			<ul>
				<li>Provide accurate, current, and complete information when requested.</li>
				<li>Maintain the security and confidentiality of any access credentials issued to you.</li>
				<li>Notify us immediately of any unauthorized use of your access.</li>
				<li>
					Accept responsibility for activities submitted through your browser session or account.
				</li>
			</ul>
			<p>We reserve the right to suspend or terminate access that violates these Terms.</p>

			<h2>4. Use of the Service</h2>
			<p>
				You agree to use the Service only for lawful purposes and in accordance with these Terms.
				You agree not to:
			</p>
			<ul>
				<li>Use the Service in any way that violates applicable laws or regulations.</li>
				<li>
					Attempt to gain unauthorized access to any part of the Service, other accounts, or
					systems.
				</li>
				<li>
					Use automated means (bots, scrapers, crawlers) to access or collect data from the Service
					without our prior written consent.
				</li>
				<li>Interfere with or disrupt the integrity or performance of the Service.</li>
				<li>Reverse engineer, decompile, or disassemble any aspect of the Service.</li>
				<li>
					Resell, redistribute, or sublicense access to the Service or any data obtained through it
					without our prior written consent.
				</li>
			</ul>

			<h2>5. Intellectual Property</h2>
			<p>
				The Service and its original content, features, functionality, and design are owned by PP2
				Studio sp. z o.o. and are protected by copyright, trademark, and other intellectual property
				laws. Our trademarks and trade dress may not be used without our prior written consent.
			</p>
			<p>
				You retain ownership of any data you upload to the Service. By uploading data, you grant us
				a limited, non-exclusive license to process it solely to provide the Service to you.
			</p>

			<h2>6. Data &amp; Analytics</h2>
			<p>
				The Service provides market intelligence, analytics, and benchmarking data for the
				restaurant industry. While we strive for accuracy, all data and insights are provided on an
				"as-is" basis. You acknowledge that:
			</p>
			<ul>
				<li>Data may be derived from third-party sources and publicly available information.</li>
				<li>
					Analytics and benchmarks are estimates and should not be the sole basis for business
					decisions.
				</li>
				<li>We do not guarantee the accuracy, completeness, or timeliness of any data provided.</li>
			</ul>

			<h2>7. Fees &amp; Payment</h2>
			<p>Access to certain features of the Service may require payment of fees. If applicable:</p>
			<ul>
				<li>Fees are as described on our pricing page or in your subscription agreement.</li>
				<li>
					All fees are quoted in EUR unless otherwise stated and are exclusive of any applicable
					taxes (such as VAT), which will be added where required.
				</li>
				<li>We reserve the right to change fees upon 30 days' notice.</li>
				<li>Failure to pay may result in suspension or termination of access.</li>
			</ul>

			<h2>8. Termination</h2>
			<p>
				We may suspend or terminate your access to the Service at any time, with or without cause,
				with or without notice. Upon termination:
			</p>
			<ul>
				<li>Your right to use the Service ceases immediately.</li>
				<li>We may delete your account and associated data after a reasonable retention period.</li>
				<li>
					Provisions that by their nature should survive termination (including intellectual
					property, limitation of liability, and governing law) will survive.
				</li>
			</ul>
			<p>
				You may terminate your account at any time by contacting us at <a
					href="mailto:hello@superextra.ai">hello@superextra.ai</a
				>.
			</p>

			<h2>9. Disclaimer of Warranties</h2>
			<p>
				To the maximum extent permitted by law, the Service is provided "as is" and "as available"
				without warranties of any kind, whether express or implied, including implied warranties of
				merchantability, fitness for a particular purpose, and non-infringement. We do not warrant
				that the Service will be uninterrupted, secure, or error-free.
			</p>

			<h2>10. Limitation of Liability</h2>
			<p>
				To the maximum extent permitted by law, PP2 Studio sp. z o.o. shall not be liable for any
				indirect, incidental, special, or consequential damages, or any loss of profits, revenue,
				data, use, or goodwill, arising from your use of or inability to use the Service. Our total
				liability for any claim shall not exceed the amount you paid us in the twelve (12) months
				preceding the event giving rise to the claim.
			</p>
			<p>
				Nothing in these Terms excludes or limits our liability where it cannot be excluded or
				limited under applicable law, including liability for damage caused intentionally.
			</p>

			<h2>11. Indemnification</h2>
			<p>
				You agree to indemnify and hold harmless PP2 Studio sp. z o.o. and its officers, directors,
				employees, and agents from any claims, damages, losses, liabilities, and expenses (including
				reasonable legal fees) arising out of your use of the Service or your violation of these
				Terms.
			</p>

			<h2>12. Governing Law &amp; Jurisdiction</h2>
			<p>
				These Terms are governed by and construed in accordance with the laws of Poland, without
				regard to conflict-of-law principles. Any dispute arising from these Terms or the Service
				that cannot be resolved amicably shall be subject to the exclusive jurisdiction of the
				Polish courts competent for the registered seat of PP2 Studio sp. z o.o.
			</p>

			<h2>13. Changes to These Terms</h2>
			<p>
				We may revise these Terms at any time by posting the updated version on this page and
				updating the "Last updated" date. Material changes will be communicated via email or a
				notice on the Service. Continued use of the Service after changes take effect constitutes
				acceptance of the revised Terms.
			</p>

			<h2>14. Severability</h2>
			<p>
				If any provision of these Terms is held to be invalid or unenforceable, the remaining
				provisions shall remain in full force and effect.
			</p>

			<h2>15. Contact Us</h2>
			<p>If you have questions about these Terms, please contact us at:</p>
			<p>
				PP2 Studio sp. z o.o.<br />
				ul. Żywiczna 9, 81-604 Gdynia, Poland<br />
				Email: <a href="mailto:hello@superextra.ai">hello@superextra.ai</a>
			</p>
		{/if}
	</div>
</article>

<Footer />
