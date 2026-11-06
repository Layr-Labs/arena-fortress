# Privacy Policy


Yukon Arena: Fortress

EFFECTIVE DATE – November 6, 2026

This Privacy Policy explains how Eigen Labs, Inc. (“Eigen Labs,” “we,” “us,” or “our”) collects, uses, and discloses personal information in connection with Yukon Arena: Fortress, including the website at https://www.yukon.org/arena-fortress, the Yukon CLI, and related APIs (collectively, the “Platform”). By using the Platform, you agree to the practices described here.

Standalone document. This policy applies only to Yukon Arena: Fortress. It is separate from and does not incorporate any Eigen Labs privacy notice governing other Eigen Labs products.

## 1. Information We Collect
Account and identity. When you sign in with GitHub, we receive from GitHub (via Supabase OAuth): your email address, GitHub username, and GitHub avatar URL. We generate and store an internal account identifier (UUID) for your account. We do not store your GitHub numeric user ID or GitHub OAuth access token.

Competition and leaderboard data. We store: your submitted code archive (`tar.gz`, in Cloudflare R2); any free-form note you attach to a submission; claimed and verified scores, challenge metrics, proof-verification results, and timestamps; submission status; git commit SHAs. API keys are stored only as a salted hash plus a short non-secret prefix, a name, and a last-used timestamp; the secret is shown once and never stored. Session tokens are stored as a hash plus expiry.

For this challenge we also store, with each submission, your public research note; your declared dependencies on prior submissions, with their rationales and evidence; the GitHub handles of any coauthors you name; the AI model and coding agent you report having used; and the automated judge's report. We determine your submission tier from your Yukon record, your scores on this challenge and the age of your GitHub account (read from GitHub's public API), and keep a record of your submissions and their status to enforce weekly submission limits. When your harness plays official games, we keep a record of every game API call it made, its model usage (tokens, cost and timing) and the game records, encrypted, in a private GitHub repository. We may also keep its output (logs) when needed to investigate a problem.

Reasoning traces and model interaction data. If you use AI coding agents or similar tools to generate or refine your submission, we may collect the reasoning traces, chat transcripts, prompts, model outputs, tool calls and results, and associated benchmark and/or verification artifacts generated during that process (“Covered Data”). You can opt out of Covered Data collection at any time by running `yukon trace off`; see Section 3 for how publication and removal work.

Technical and log data. Our API reads your IP address from edge headers to enforce rate limits; IP addresses are not written to our application database. Our hosting providers (Vercel for the website, Fly.io for the API) automatically log request IP, user agent, path, status, timing, and approximate location, and this is platform-level logging outside our application code. Our API logs method, route, status, duration, request ID, and your email for authenticated requests; these logs go to Datadog. Datadog also receives aggregate metrics (counters and timings) that use non-personal tags only and do not include individual user identifiers.

Cookies. Supabase sets HttpOnly, Secure cookies to maintain your login session. We set no advertising or tracking cookies. We use Google Analytics on the website (see Section 7).

CLI telemetry. The CLI collects limited telemetry by default: CLI name and version, command name, success or error, duration, and optional benchmark ID. It does not collect your OS, hardware identifiers, hostname, file paths, arguments, or source code. You can disable telemetry at any time by running `yukon config --telemetry disabled`. This basic telemetry is separate from Covered Data collection, which is controlled by `yukon trace off`.

## 2. How We Use Information
We use the information we collect to authenticate you; accept, evaluate, verify, and display submissions; operate the leaderboard; review submissions for attribution, fair play and permitted content using an automated, AI-based judge before promotion; determine your submission tier and enforce submission limits; enforce rate limits and prevent abuse; monitor platform reliability; send you account and submission emails; and comply with legal obligations. Where you have not opted out, we also use Covered Data to develop, train, fine-tune, and evaluate machine-learning models and datasets, and may publish a pseudonymized, filtered version of it as part of a public dataset, as described in Section 3. We use Google Analytics to understand aggregate website usage.

## 3. What We Make Public
The leaderboard is public. For each submission, it exposes your GitHub username, avatar URL, profile link, internal account UUID, submission note, scores and metrics, submission status, timestamps, and commit SHAs. Every submission is also pushed to a public GitHub repository branch and opened as a public pull request, making your code publicly auditable. For this challenge, your public research note, declared dependencies and their rationales, coauthors, the AI model and coding agent you report using, per-task results and metrics, and the automated judge's report are also public. Your harness's output and the per-game records of official games are not published during the season.

Your submitted proofs, code, notes, verification artifacts, evaluation records, and promotion commits may be public. Do not include sensitive personal data, credentials, secrets, confidential information, trade secrets, or anything else you do not have the right to disclose or do not want publicly disclosed in any submission or related material.

Git commit history: read before submitting. Every scored submission is pushed to a public branch of the challenge repository, and its candidate commit ordinarily includes a Co-authored-by: trailer identifying you by your GitHub username and a GitHub-generated noreply email address, not your account email or real name. If your submission is promoted, that attribution becomes part of the repository’s shared challenge branch. This disclosure is permanent and public in the GitHub UI, via the GitHub API, in clones and forks, and in third-party git indexing services. It cannot be removed. By submitting, you explicitly consent to this disclosure.

Covered Data: additional uses and publication. By participating without opting out, you grant Eigen Labs a worldwide, royalty-free, non-exclusive, perpetual, sublicensable, transferrable license to use, reproduce, modify, create derivative works of and from, analyze, and use to develop, train, fine-tune and evaluate machine-learning models and datasets, and publish or distribute your Covered Data, and to grant further rights in your Covered Data to third parties. Any public release of Covered Data as part of a public dataset will be under the terms of a data license that we will make publicly available at or before the time we first publish any Covered Data. We will not publish your Covered Data until we publish that license at a publicly accessible URL, but we may otherwise use Covered Data as permitted by the above license grant. This disclosure is separate from, and in addition to, the leaderboard and git-history disclosures described above.

Pseudonymization and filtering are best-effort, not guaranteed. Before any publication of Covered Data, we run an automated pipeline that removes payloads, replaces identifiers with pseudonymous tokens, scrubs credentials and personal data, and applies a privacy filter. No automated filter is perfect. Pseudonymization is not anonymization, filtering may miss sensitive content, and once published, data may be copied, cached, mirrored, and indexed by third parties and cannot be fully retracted. You should not enter anything you would not want published into your agent session, prompts, or submissions.

You may opt out of Covered Data collection at any time by running `yukon trace off`, without affecting your ability or eligibility to participate in any challenge, your score, or your leaderboard placement. You may also request that already-collected Covered Data be removed from any published dataset by contacting [notices@eigenlabs.org](mailto:notices@eigenlabs.org) (see “Retention,” below, for what removal does and does not reach).

## 4. How We Disclose Information
We share your information only as necessary to operate the Platform:

- GitHub: OAuth identity provider; host of public submission repos and permanent commit history including Co-authored-by trailers; provider of the GitHub Actions workflows that build and score submissions, and host of the private repository where we store encrypted game records and the submission ledger.
- OpenRouter: routes your harness's model calls during official games to the challenge's fixed model, and routes the automated judge's model calls, which include your submission's code changes, research note, declared dependencies, and the GitHub handles of you and your coauthors.
- AI model providers: Together AI, which serves the challenge's fixed model, receives the content of your harness's model calls during official games; the provider of the automated judge's model (currently OpenAI through OpenRouter, or Anthropic through Amazon Bedrock) receives the judge's inputs described above.
- Supabase: GitHub OAuth broker, session/JWT issuer, and hosted Postgres database.
- Cloudflare R2: Storage for submitted code archives.
- Vercel: Website hosting; edge logs include IP and user agent.
- Fly.io: API hosting; edge logs include IP and user agent.
- Datadog: Application logs and metrics, including your email address in authenticated request logs.
- Google LLC: Google Analytics on the website.
- Hugging Face: hosts the public dataset of pseudonymized, filtered Covered Data, for users who have not opted out.

Where you have not opted out, Covered Data we publish may also be further used, licensed, or redistributed by downstream recipients under the data license described in Section 3.

If we publish a public, pseudonymized Covered Data dataset on Hugging Face or equivalent sites, data published there is downloadable worldwide, subject to any access gating we apply. We do not sell personal information for money. Some privacy laws may treat publication of a public dataset as “sharing” or a “sale” of personal information; see Section 9 for how we address this and your opt-out rights. We do not share personal information for cross-context behavioral advertising.

## 5. Legal Bases (EU/UK Users)
If you are in the EEA or UK, we process your personal data under these legal bases:

- Contract performance: Providing the Platform, running evaluations, and maintaining the leaderboard.
- Legitimate interests: Platform security, abuse prevention, debugging, aggregate analytics and analyzing Covered Data to improve challenge design and evaluation. We have assessed that these do not override your rights.
- Consent: publication of your pseudonymized Covered Data as a public dataset, Google Analytics, and, to the extent required, CLI telemetry. Your consent to publication is optional and separate from participation; you may withhold or withdraw it at any time (see Sections 3, 6, and 9) without affecting your ability to participate. Internal analysis of Covered Data to improve challenges relies on legitimate interests; publication to the public relies on your consent.
- Legal obligation: Where required by applicable law.

## 6. Retention
We retain personal information as long as your account is active or as necessary to provide the Platform, comply with legal obligations, and resolve disputes. In general: account and identity data is retained for the life of your account plus a reasonable period after deletion; submission archives are retained for the duration of the challenge and thereafter as required; leaderboard scores and metrics are retained as part of the permanent competition record; application logs are retained per our Datadog configuration for a reasonable period for operational and security purposes; CLI telemetry events are retained for a reasonable period for operational and security purposes; the records of official games, and any harness output we keep, are retained, encrypted, in a private repository for the duration of the season and 12 months thereafter. Promotion commit history is permanent and cannot be deleted.

Covered Data. If you request removal of already-collected Covered Data by contacting [notices@eigenlabs.org](mailto:notices@eigenlabs.org), we will remove it from our own published dataset and any subsequent release we control, and delete it from our internal systems, subject to reasonable operational exceptions, no later than our next scheduled release. We will use reasonable efforts to notify known downstream licensees of your removal request. However, because Covered Data may already have been downloaded, copied, or used to train models or build tools by third parties before your request, we cannot remove it from copies outside our control, and removal does not affect any model or tool already built using that data. This timeline and these limitations apply in place of the 30-day timeline described below for general account-deletion requests.

To request deletion of your account and personal data, contact us at [notices@eigenlabs.org](mailto:notices@eigenlabs.org). We will respond within 30 days, subject to our legal obligations and the permanent nature of public git history.

## 7. Cookies and Tracking
Authentication cookies. Supabase sets HttpOnly, Secure session cookies. These are strictly necessary for the Platform to function.

Google Analytics. We use Google Analytics on the website to understand aggregate usage. Google Analytics uses cookies and collects IP address (subject to anonymization) and browsing behavior. You can opt out via the Google Analytics opt-out browser add-on.

We use no advertising cookies and no cross-site tracking.

## 8. International Transfers
Eigen Labs is based in the United States. If you are in the EEA or UK, your personal data may be transferred to and processed in the US. We rely on Standard Contractual Clauses (SCCs) approved by the European Commission, and the UK IDTA or UK Addendum as applicable, for these transfers.

Separately, if you do not opt out, your pseudonymized Covered Data may be published in a public dataset downloadable worldwide. This publication is not covered by SCCs or any other transfer mechanism; it rests on your consent and on the pseudonymization and filtering described in Section 3. If you do not want this global disclosure, do not consent to publication.

## 9. Your Privacy Rights
EU/UK (GDPR / UK GDPR). You have rights of access, rectification, erasure, restriction, portability, and objection, and the right to withdraw consent. To exercise these rights, contact us at [notices@eigenlabs.org](mailto:notices@eigenlabs.org). We will respond within 30 days. You also have the right to lodge a complaint with your local data protection authority.

California (CCPA/CPRA). You have the right to know, delete, correct, and opt out of the sale or sharing of your personal information. We do not sell or share personal information. Contact us at [notices@eigenlabs.org](mailto:notices@eigenlabs.org); we will respond within 45 days.

For Covered Data that has already been published as part of a dataset, erasure, deletion, and opt-out-of-sale/sharing requests are subject to the limitations described in Section 6 (Retention): we can remove it from our own systems and controlled releases, but cannot reach copies already made, or models already trained, by third parties outside our control.

## 10. Children’s Privacy
The Platform is not directed to users under 13 (or under 16 in the EEA/UK). We do not knowingly collect personal information from children. If you believe we have done so, contact us at [notices@eigenlabs.org](mailto:notices@eigenlabs.org) and we will delete it promptly.

## 11. Changes to This Policy
We may update this policy from time to time. When we make material changes we will update the date above and, where appropriate, notify you by email or platform notice. Continued use after the effective date constitutes acceptance.

## 12. Contact
For questions about this policy or to exercise your privacy rights:

Eigen Labs, Inc.
600 1st Ave Ste 330 # 926277
Seattle, WA 98104-2246
notices@eigenlabs.org
