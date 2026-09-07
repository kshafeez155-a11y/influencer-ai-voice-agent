# TAC Voice UI Revamp Rulebook

Status: product and design standard  
Applies to: public web experience and future consumer mobile app  
Primary audience: mobile-first fans discovering TAC Voice through a creator link or social post

The words **must**, **should**, and **may** are intentional. A must is an acceptance requirement, a should needs a documented reason to break, and a may is optional.

## 1. Product thesis

TAC Voice is not an AI infrastructure company in the public experience. It is a social entertainment product where a fan can receive a fun, clearly disclosed AI call from a creator they recognize.

The public product has one job:

> Help a fan trust the experience enough to request their first creator call in under 60 seconds.

The emotional sequence is:

> Recognize the creator -> hear the voice -> imagine the conversation -> understand what happens -> request the call -> share the moment.

Every public screen must support that sequence. Provider names, model versions, latency benchmarks, system health, admin terminology, and implementation details do not belong in the fan journey.

## 2. Experience principles

### 2.1 Creator first

- A creator's face, name, voice, and personality must appear before TAC technology.
- The first viewport must contain at least one recognizable person or authentic creator asset.
- A waveform may support a creator; it must not replace one.
- Use **creator** in fan-facing copy. Do not use subject, persona, node, agent, protocol, synthesis, or initiate contact.

### 2.2 Demonstrate before asking

- Every creator profile must offer a 5–12 second voice preview before the phone-number form.
- The preview must be playable without login and without entering personal information.
- Suggested conversation starters must appear before the call action.
- Do not ask for a phone number on the landing-page hero.

### 2.3 Familiar, not luxurious

- The interface should feel as easy as opening a creator profile in a social app.
- Prefer clear labels, circular avatars, visible reaction/share controls, strong photography, and comfortable touch targets.
- Avoid gallery-like whitespace, fashion-editorial typography, technical dashboards, and luxury-brand restraint.
- Casual does not mean careless: spacing, type, states, and alignment must remain systematic.

### 2.4 Honest at every step

- Always call the experience an AI call or AI voice call.
- Never claim that a voice is indistinguishable from a real person.
- Show creator authorization or clearly label fictional/demo personas.
- Do not display “Online” unless it represents measured call availability.
- Do not display “All systems operational” when required call providers are not configured.
- Never show a clickable control that does nothing.

### 2.5 Mobile is the primary canvas

- Design at 390px before adapting to desktop.
- No public action may require hover.
- The primary call action must be reachable within one thumb movement after a fan decides to act.
- Pages must have zero horizontal overflow at 320px, 360px, 390px, 430px, 768px, and 1440px.

## 3. Brand direction

### 3.1 Personality

TAC Voice should be:

- Social
- Playful
- Direct
- Creator-led
- Slightly surprising
- Transparent about AI

It should not be:

- Corporate AI
- Cyberpunk
- Luxury editorial
- A developer console
- A deepfake novelty site
- A clone of Instagram, TikTok, or any one social network

### 3.2 Visual signature

The signature element is the **incoming creator call**:

- A large circular creator portrait
- Two restrained call rings around the portrait
- A small voice pulse attached to the portrait while audio plays
- Clear caller-name typography
- Familiar accept-call energy without copying a phone operating system

Use this motif in the hero, loading state, confirmation state, and share card. Do not scatter unrelated decorative motifs across the site.

### 3.3 Color tokens

Use this base palette unless a later brand study replaces the complete system:

| Token | Value | Use |
|---|---:|---|
| Canvas | `#F7F8FA` | Page background |
| Surface | `#FFFFFF` | Cards, sheets, inputs |
| Ink | `#17181C` | Primary text |
| Muted | `#686D76` | Secondary text |
| Line | `#E4E7EC` | Dividers and field borders |
| Call coral | `#FF3D63` | Primary fan action |
| Success green | `#159A5B` | Confirmed call states only |
| Soft coral | `#FFE7EC` | Selected and supportive states |

Rules:

- Call coral is reserved for the primary action, active states, and call-related emphasis.
- Green means success or real availability; it is not decoration.
- Creator photography supplies most page color.
- Do not use gradients in the base interface.
- Do not create a rainbow palette from persona categories. Use creator images and one optional profile accent extracted with contrast checks.

### 3.4 Typography

- Primary family: **Figtree**, with `system-ui, sans-serif` fallback.
- Use one family throughout the public product. Personality comes from scale, weight, copy, and creator assets—not gratuitous font pairing.
- Hero: 44/46 mobile, 68/70 desktop, weight 750–800.
- Page title: 32/36 mobile, 44/48 desktop, weight 700.
- Card title: 18/24, weight 650–700.
- Body: 16/24, weight 400–500.
- Supporting text: 14/20. Never use body-critical text below 14px.
- Utility labels may be 12/16 only for timestamps, counts, or metadata.
- Use sentence case. Avoid letter-spaced all-caps except short verified/status labels.

### 3.5 Shape, borders, and depth

- Creator avatars are circular.
- Content cards use 16px radius.
- Inputs and buttons use 12px radius.
- Chips use 999px radius only when they are genuinely tags or filters.
- Default borders are 1px `Line`.
- Use shadows only for elevated sheets, sticky call bars, or transient menus.
- Maximum ordinary shadow: `0 8px 24px rgba(23, 24, 28, 0.10)`.
- Do not put every section in a card. Page structure and whitespace must do most grouping.

### 3.6 Motion and sound

- The signature motion is one incoming-call ring sequence lasting no more than 1.2 seconds.
- Audio playback may animate a small pulse around the creator avatar.
- Ordinary transitions are 120–200ms and affect color or opacity.
- Do not scale whole cards on hover.
- Respect `prefers-reduced-motion` and never autoplay audio.

## 4. Information architecture

### 4.1 Public navigation

Mobile:

- TAC wordmark/home
- Explore
- Search
- Optional account/avatar only after real authentication exists

Desktop:

- TAC Voice
- Explore creators
- How it works
- For creators
- Primary action: Explore creators

Remove Login until authentication has a real fan benefit and works end to end. Remove Pricing until a price exists. System status belongs on an ops/status page, not in public navigation.

### 4.2 Landing page order

1. Creator-led hero with immediate “Hear a call” preview
2. Horizontally scrollable popular creators on mobile
3. Three-step explanation using actual screens or call states
4. Trust and safety explanation
5. Real reactions or call moments once available
6. “Request a creator” growth action
7. Final creator grid and CTA

Do not lead with architecture, provider metrics, generic feature cards, or a decorative waveform.

### 4.3 Explore page

- Search sits at the top and remains visible while browsing.
- Start with useful groups: Popular now, New voices, Fitness, Business, Entertainment.
- Hide empty categories.
- With fewer than eight creators, use one curated list rather than a directory taxonomy.
- Creator cards must show a photo, name, verification state, concise role, preview control, and call action.
- Filtering must operate correctly or not appear.

### 4.4 Creator profile

Order on mobile:

1. Back and Share
2. Creator portrait, name, verification, role
3. AI disclosure and creator approval
4. Voice preview
5. Three conversation starters
6. Call expectations: price, ring time, duration, language
7. Phone form
8. Bio and secondary information

The mobile call action becomes sticky only after the user scrolls past the first inline action. It must never cover form errors or the browser safe area.

### 4.5 Call states

Use one vocabulary throughout:

- Primary action: **Get a call**
- Loading: **Starting your call…**
- Success: **Your phone should ring in about 10 seconds**
- Failed configuration: **Calls are temporarily unavailable. Try again later.**
- Invalid number: **Enter a valid phone number including country code.**

Never expose provider names, credentials, call SIDs, stack traces, or operator instructions to fans.

## 5. Core screen blueprints

### 5.1 Landing hero

```text
TAC Voice                         Explore

Your favorite creators,
calling you.

Pick someone. Hear their AI voice.
Get a real phone call in seconds.

[creator portrait with call rings]
Priya Sharma  ✓  Creator-approved AI
[▶ Hear Priya's voice]

[Explore creators]
No app · No signup · Clearly AI
```

### 5.2 Creator card

```text
[large creator photo]

[✓] Priya Sharma
Marketing creator

▶ 0:08 voice preview

[Get a call]        [Share]
```

Cards must not contain provider names, “active node,” latency, model versions, or technical status.

### 5.3 Call form

```text
Get a call from Priya
Usually rings in about 10 seconds

Your name (optional)
[Sam                         ]

Mobile number
[country] [number            ]

[ ] I agree to receive this AI-generated call.

[Call my phone]

Free today · Up to 5 min · We do not sell your number
```

Consent must be unchecked by default when legally required, must be required by validation, and must link to a real privacy notice.

## 6. Content rules

- Write from the fan's point of view.
- Prefer verbs people recognize: hear, call, ask, talk, share, explore.
- One sentence should perform one job.
- Creator taglines must be concrete: “Fitness coach for first-time marathoners,” not “Empowering your ultimate journey.”
- Conversation prompts must sound speakable.
- Avoid “unlock,” “reimagine,” “revolutionize,” “seamless,” “cutting-edge,” “high-fidelity,” “next-generation,” and “powered by” unless technically necessary.
- Do not invent testimonials, usage counts, availability, ratings, or creator approval.
- Do not write fake social activity to make the product feel busy.

## 7. Trust and safety requirements

Every creator must have one visible state:

- **Creator approved** — approval is documented
- **Official fictional character** — rights are documented
- **Demo persona** — clearly fictional and not presented as a real creator

Every public call flow must state:

- That the caller is AI
- Whether the call is recorded or transcribed
- How the phone number is used and retained
- Cost or carrier-charge expectations
- Expected ring time and caller-ID behavior
- How to stop or report a call

Privacy, Terms, Safety, and Report links must lead to real pages before public acquisition campaigns begin.

## 8. Accessibility and responsive acceptance

- Meet WCAG 2.2 AA contrast for text and controls.
- All interactive elements must be keyboard reachable with visible focus.
- Touch targets must be at least 44x44 CSS pixels.
- Inputs require persistent labels; placeholders are examples, not labels.
- Errors must be attached to fields and announced with `aria-live` where appropriate.
- Images require meaningful alt text; decorative images use empty alt text.
- Failed images must fall back to initials or a local placeholder without layout shift.
- Test at 200% zoom and with reduced motion.
- Do not hide scrollbars globally.
- No text, controls, or media may be clipped at supported widths.

## 9. Performance requirements

- Do not ship Tailwind's browser CDN in production.
- Self-host or precompile critical styles.
- Use responsive AVIF/WebP creator images with declared dimensions.
- Load only required font weights and use `font-display: swap`.
- Landing-page LCP should be a useful creator asset, not an empty decorative panel.
- Target LCP under 2.5s and CLS under 0.1 on a mid-tier mobile connection.
- A failed font, image, analytics, or provider request must not break navigation or the call form.

## 10. Acquisition instrumentation

Track, without storing raw phone numbers in analytics:

- Landing viewed
- Creator card viewed
- Creator profile viewed
- Voice preview started/completed
- Conversation prompt selected
- Call form started
- Validation failed by reason
- Consent accepted
- Call requested
- Call request failed by safe error category
- Call connected/completed when backend callbacks exist
- Profile shared
- Creator requested

The primary funnel is:

> Landing view -> creator profile -> preview played -> form started -> call requested -> call connected

Design changes must be evaluated against this funnel, not only subjective preference.

## 11. Revamp order

1. Repair the live profile route, responsive overflow, broken images, fake controls, and consent validation.
2. Remove misleading status, login, pricing, category, and infrastructure UI.
3. Replace the hero with one real creator-led call moment.
4. Redesign the creator card and profile around preview, prompts, trust, and call expectations.
5. Add sharing and request-a-creator loops.
6. Add real analytics and evaluate the first-call funnel.
7. Only then add account, pricing, community, or broader directory features.

## 12. Definition of done

A public-screen revamp is not complete until:

- All visible controls work.
- The complete first-call path works on desktop and mobile.
- No required provider is represented as available when unavailable.
- A first-time user can explain the product after five seconds.
- A user can hear a voice before sharing a phone number.
- AI disclosure and creator authorization are visible.
- The page has no horizontal overflow at the required widths.
- Keyboard, screen-reader basics, reduced motion, failed images, loading, empty, success, and error states have been tested.
- Funnel events are recorded with no sensitive phone data.

