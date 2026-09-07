# TAC Voice Anti-AI-Slop Rulebook

Status: mandatory review standard for AI-assisted frontend work  
Applies to: public site, app, admin surfaces, generated copy, and future design-system components

This rulebook does not ban AI-assisted code, component libraries, gradients, cards, or popular patterns. It bans using them without product-specific reasons. The problem is not polish; it is unearned sameness.

## 1. Working definition

AI slop is an interface whose visual, structural, or verbal decisions appear to come from generic generation defaults rather than TAC Voice's users, content, and workflow.

The test is simple:

> If TAC Voice's name and colors were replaced, could this be any AI SaaS landing page?

If yes, the work is not ready.

Research and current design criticism consistently identify two causes:

1. Underspecified prompts make generators choose common training-data defaults.
2. Local “make this section better” iterations preserve accidental foundations and create inconsistent exceptions.

The solution is to define product intent, real content, exact tokens, and global constraints before generation, then review the complete experience.

## 2. The TAC evidence rule

Every prominent design decision must be justified by at least one of:

- A fan need
- A creator behavior
- The phone-call workflow
- A real content constraint
- Accessibility
- Measured acquisition evidence
- An explicit TAC brand rule

“It looks modern,” “it feels premium,” “AI generated it,” “it is a common pattern,” and “it looks good on Dribbble” are not valid justifications.

Examples:

- Circular portraits are earned because creators are people and social identity is central.
- A call ring animation is earned because receiving a call is the product's signature moment.
- A three-card feature row is not earned merely because the product has three benefits.
- A bento grid is not earned unless different content truly requires different visual weight.

## 3. Default-output patterns to reject

These are **banned by default**, not universally forbidden. An exception requires a written product reason in the PR or task notes.

### 3.1 Generic structure

- Centered hero with eyebrow, gradient headline, paragraph, and two CTAs
- Hero followed immediately by three equal feature cards
- Logo cloud with invented or context-free logos
- Bento grid used as a synonym for “modern”
- Alternating left-text/right-image feature bands repeated down the page
- Testimonial carousel without verified testimonials
- Pricing table before a real pricing model exists
- Final full-width gradient CTA banner
- Dashboard shell with sidebar, four metric cards, chart, and table regardless of workflow
- A separate card around every piece of content

### 3.2 Generic visual language

- Indigo-to-violet or purple-to-blue gradients
- Gradient-filled headline text
- Decorative aurora blobs, glow halos, and blurred color clouds
- Glassmorphism or translucent floating panels without a spatial reason
- Dark mode used to make an unfinished product appear premium
- Excessive `rounded-2xl`/`rounded-3xl` surfaces
- Pills used for ordinary buttons, labels, navigation, and containers
- Large soft shadows on every surface
- Thin gray borders around every element
- Random neon accent colors competing for attention
- Generic outline icons inside colored rounded squares
- Decorative waveforms unrelated to playable audio
- Emoji used as substitute product icons
- Stock illustrations of abstract AI brains, robots, sparkles, or circuit heads

### 3.3 Generic typography

- Inter, Geist, or another generator default used without an explicit typography decision
- Oversized `text-6xl` headings chosen before testing the actual copy
- A serif display face added only to imply luxury
- Monospaced uppercase labels used to imply technical credibility
- Eyebrow labels above every section heading
- Three or more unrelated type families
- Tiny gray text used to make layouts look refined

The font itself is not the offense. Unexamined default use is.

### 3.4 Generic motion

- Everything fading upward on scroll
- Cards lifting and scaling on every hover
- Continuous ambient animation with no state meaning
- Animated gradient backgrounds
- Staggered page-load animation that delays comprehension
- Fake real-time dots, status pulses, or typing indicators

Motion must communicate calling, listening, connecting, success, interruption, or another real product state.

### 3.5 Generic copy

Reject headlines and labels built from:

- “Reimagine…”
- “Unlock the power of…”
- “The future of…”
- “Built for the way you…”
- “Where X meets Y”
- “Seamless, powerful, effortless”
- “Elevate your experience”
- “Next-generation”
- “Cutting-edge”
- “Supercharge”
- “Transform your workflow”
- “Your X, redefined”

Also reject:

- Three-item adjective lists that say nothing
- Fake precision such as unsupported latency or success claims
- Decorative pseudo-technical language
- Labels that describe implementation rather than user intent
- Repeated em dashes and formulaic “not X—Y” constructions
- Testimonials, counts, company logos, and social activity that are not real

For TAC Voice, name the person and the action: “Hear Priya's AI voice,” “Ask Marco about buying your first home,” “Get a call in about 10 seconds.”

## 4. Rules for generating a new screen

Before an AI agent writes markup or CSS, the brief must contain:

1. **Audience:** the specific person using the screen.
2. **Single job:** the one outcome the screen owns.
3. **Real content:** actual names, longest likely labels, real images or explicit fallbacks, and real states.
4. **Hierarchy:** the first, second, and third things a user should notice.
5. **Constraints:** viewport range, accessibility, loading/error/empty states, and existing system rules.
6. **Tokens:** exact colors, type scale, spacing, radius, and shadow values.
7. **Signature:** the one TAC-specific moment allowed to be visually expressive.
8. **Banned defaults:** the relevant list from this rulebook.

Do not begin from “make a modern, premium landing page.” Do not begin implementation until the brief can explain why the composition belongs to TAC Voice.

## 5. Product-content-first process

### Pass 1: content inventory

List every real item that must appear, including long creator names, missing avatars, unavailable calling, optional names, international phone numbers, disclosure, and errors.

### Pass 2: grayscale hierarchy

Design the screen without brand color. If hierarchy depends on gradients or neon, it is not strong enough.

### Pass 3: one visual signature

Spend expressive energy on the incoming creator call. Keep navigation, forms, and supporting content quiet.

### Pass 4: token application

Use only named design tokens. Do not introduce one-off colors, radii, shadows, or page widths because a generated section “looks better.”

### Pass 5: complete-state review

Review loading, populated, empty, error, disabled, success, broken-image, long-copy, keyboard-focus, reduced-motion, and offline/provider-unavailable states.

### Pass 6: cross-page review

Capture the landing page, explore page, creator profile, call form, success state, and admin view together. Fix system inconsistencies instead of patching one page locally.

## 6. Composition rules

- Each viewport gets one dominant focal point.
- Every section must introduce a new user question or action; otherwise merge or remove it.
- Use whitespace to group content before adding a container.
- A card must express a discrete object, action, or state—not merely decorate a paragraph.
- Unequal content should not be forced into equal cards.
- Asymmetry must follow importance, not visual novelty.
- Page width must follow content: a reading column, a creator feed, and an admin table should not share one arbitrary max width.
- Repetition must teach the interface. Do not vary the same button, card, or label without a semantic reason.
- Do not add decorative elements until the page works with text, images, and controls alone.

## 7. Component rules

### Buttons

- One primary action per region.
- Labels state the result: “Get a call,” not “Continue” or “Submit.”
- No gradient buttons, glow, or icon-only primary actions.
- Pills are allowed only for compact actions that semantically behave like chips.

### Cards

- Use the smallest radius and shadow that express the intended layer.
- Do not nest cards merely to create depth.
- Creator cards must prioritize portrait, name, voice preview, and action.
- Avoid identical icon-title-paragraph cards unless the content is genuinely parallel.

### Navigation

- Do not include future, fake, or non-functional destinations.
- Do not place operational status in consumer navigation.
- Mobile navigation must be designed, not produced by hiding desktop links.

### Forms

- Forms must connect to real behavior or be clearly marked as prototypes outside production.
- Use persistent labels and specific error recovery.
- Do not pre-check consent as decoration or ignore its value on submit.
- Never display secrets, provider details, stack traces, or internal IDs to users.

### Empty and loading states

- Skeletons must match the eventual layout.
- Loading states cannot run indefinitely without recovery.
- Empty states explain what is absent and give one useful next action.
- Do not use animation to disguise broken data.

## 8. The anti-slop review tests

Every generated or materially redesigned screen must pass all tests.

### 8.1 Five-second test

Show the screen for five seconds. A reviewer should answer:

- What is this product?
- Who is this creator?
- What can I do now?
- Is the call real or AI?

### 8.2 Brand-swap test

Remove TAC's name and coral accent. If the page could sell an AI note-taker, analytics tool, or crypto product without structural changes, reject it.

### 8.3 Screenshot-silhouette test

Blur the screenshot. It should not reduce to centered hero + three cards + card grid + final banner.

### 8.4 Real-content test

Replace sample content with:

- A 28-character creator name
- A two-line role
- A missing avatar
- An unavailable call provider
- A validation error
- A 20-character international number

The layout must remain usable.

### 8.5 Interaction-honesty test

Click every visible control. Each must navigate, change state, submit, or clearly explain why unavailable. No `href="#"`, swallowed form submissions, fake filters, fake login, or decorative checkboxes.

### 8.6 Restraint test

Count decorative techniques: gradients, shadows, glows, glass, blobs, animated backgrounds, oversized radius, illustration, and ornamental type. If more than one drives the screen, remove until one signature remains.

### 8.7 Product-language test

Search the UI for generic AI copy and internal terminology. Every remaining phrase must sound like something a fan would say or need.

### 8.8 Mobile test

Review screenshots at 320, 360, 390, and 430px. Verify no clipping, horizontal scroll, hover dependency, hidden primary action, covered errors, or sub-44px essential targets.

## 9. AI-agent implementation contract

Use this block in future UI implementation requests:

```text
Read docs/UI_REVAMP_RULEBOOK.md and docs/ANTI_AI_SLOP_RULEBOOK.md before editing.

State the screen's audience, single job, content hierarchy, and TAC-specific
signature before implementation. Use real project content. Do not introduce
gradients, glassmorphism, glow, bento grids, generic three-card sections,
eyebrow labels, fake controls, fake social proof, infrastructure language,
or new design tokens without an explicit product reason.

Implement all loading, empty, error, disabled, success, long-content, and
broken-image states. Verify at 320, 390, 768, and 1440px, with keyboard focus
and reduced motion. Capture screenshots and run the brand-swap,
interaction-honesty, and real-content tests before declaring completion.
```

## 10. Pull-request acceptance checklist

- [ ] The screen has a named audience and single job.
- [ ] The first three items in the visual hierarchy are intentional.
- [ ] Real content—not lorem ipsum or invented proof—was used.
- [ ] The composition is specific to a creator phone-call product.
- [ ] Only approved tokens were used.
- [ ] One visual signature is present at most.
- [ ] Generic gradients, glows, glass, bento, and equal-card defaults are absent or justified.
- [ ] Copy contains no AI-marketing filler or internal technology language.
- [ ] All controls work.
- [ ] All important states exist.
- [ ] Mobile widths, keyboard focus, contrast, reduced motion, and 200% zoom pass.
- [ ] The complete acquisition path was tested, not only the edited component.
- [ ] Before/after screenshots are attached.

## 11. Sources reviewed

These sources informed the pattern inventory; TAC-specific rules and thresholds above are design decisions for this product.

- [Interrogating Design Homogenization in Web Vibe Coding](https://arxiv.org/abs/2603.13036) — research framing for homogenization and “productive friction.”
- [Why vibe-coded websites end up looking the same](https://blog.interfacekit.io/why-vibe-coded-websites-look-the-same) — generic beginnings, local optimization, prototype ratchet, and system drift.
- [7 Signs a UI Has Been Vibe Coded](https://www.thefountaininstitute.com/blog/signs-vibe-coded-ui) — common visual symptoms including purposeless neon, dark glow, and weak hierarchy.
- [Why every AI-built site looks the same](https://styles.gallery/blog/why-ai-built-sites-look-the-same) — default component styling, AI purple, gradient headlines, centered heroes, and equal feature-card structures.
- [no-slop-ui](https://github.com/LeoStehlik/no-slop-ui) — an open rule set covering glassmorphism, gradient abuse, excessive rounding, decorative copy, dashboard sludge, and review gates.

The sources do not make every popular pattern inherently bad. The shared lesson is that an unexamined combination of defaults makes unrelated products converge. TAC Voice must earn its design from creators, fans, and phone calls.

