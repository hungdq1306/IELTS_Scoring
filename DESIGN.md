# FogWrite — Screen Design 01

The six-screen UI specification supplied by the user supersedes the earlier editorial/inline-SVG direction.

## Tokens

- Brand: FogWrite, subtitle IELTS Writing Studio.
- UI and headings: Plus Jakarta Sans; ink #132A26; secondary #526B66.
- Canvas #F6FAF8; cards #FFFFFF with #DCE8E3 border, 16px corners and 0 2px 10px rgba(15,76,67,.04) shadow.
- Sidebar #0F4C43; active navigation #236B60 with 12px corners.
- Primary action #0E6258, hover #0B4F47, white text, 12px corners.
- Mint banner #E6F2ED; strength #D6F3E3 / #135E37; suggestion and band #FCE6CC / #8C4312; error #FADBD8 / #991B1B with #E5534B underline.
- UI icons: lucide-react, 1.75px strokes.

## Screen composition

1. Landing: no sidebar; frog logo, navigation and Sign in; two-column hero; white sample feedback card with writing PNG overlapping the bottom-right corner; three equal feature cards.
2. Topics: dark sidebar; prompt heading; mint Surprise me banner with a peeking PNG on its top edge; four filter pills; four initial prompt cards in two columns.
3. Writing: timer, save state and live word count; 4/8 prompt/editor columns; compact formatting/list toolbar; sleeping PNG beside autosave text; submit action on the right.
4. Assessment: 8/4 essay/score columns; honest annotation legend; selected-passage popover; peach band badge and criterion rows; encouraging PNG beside a speech bubble.
5. Criterion: 7/5 essay/detail columns; segmented criterion tabs; strengths, development and quote cards; pointing PNG on the Next step card; full-width practice action.
6. Skill practice: back link, title, actual exercise progress; 4/8 source/editor columns; hint and answer actions; peach feedback banner with a lilypad PNG.

## Character rules

See [PNG asset mapping](docs/MASCOT_ASSETS.md). There are no inline frog SVGs. Every character comes from a fixed local transparent PNG through FrogMascot.tsx. Never restore the old arm/head rigs or use a custom-drawn fallback. Keep the five primary studio links; signed-in accounts also see classes, authorized administration and the bottom profile menu.

## Product truth

Sample assessments and sample exercises are labelled. Live feedback comes from the existing APIs. Criterion evidence is neutral unless its data explicitly identifies it as a strength or suggestion. The pilot Sign in button opens Clerk. The separate local demo explains its browser-session storage.

## Verification limits

The reference image could not be downloaded in the implementation environment. The implementation follows the supplied screen-by-screen specification. All six screens passed headless Chromium screenshot and interaction checks at 1440x900 and 1280x800. Pixel-identical comparison remains unconfirmed because the reference image could not be downloaded and the offline checker uses fallback fonts.
