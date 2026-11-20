# FogWrite PNG mascot assets

The hand-drawn SVG character implementation has been removed. `frontend/src/components/FrogMascot.tsx` is the only character renderer and accepts a typed variant. It renders an image with `object-contain`, no pointer interaction and `draggable={false}`. An unavailable image becomes a small FW badge; there is no SVG character fallback.

| Variant | Public PNG | Placement |
| --- | --- | --- |
| logo | /mascots/frog-logo.png | Header and sidebar wordmark |
| writing | /mascots/frog-writing.png | Landing feedback card, bottom-right overlap |
| peeking | /mascots/frog-peeking.png | Topic banner top edge, paws aligned with the border |
| sleeping | /mascots/frog-sleeping.png | Writing footer, beside autosave status |
| encouraging | /mascots/frog-encouraging.png | Assessment overview, left of the speech bubble |
| pointing | /mascots/frog-pointing.png | Criterion Next step card, bottom-right |
| lilypad | /mascots/frog-lilypad-smile.png | Exercise feedback banner, bottom-right; Overview callout |

The seven images are generated raster illustrations with transparent RGBA channels. Individual assets are trimmed from the generated pack and retain their original aspect ratios. Character drawing data is never embedded in React components. UI symbols come from `lucide-react`.

Both Vite and the offline build copy `frontend/public/mascots` into the served build. Changes to the JavaScript and CSS update their content hashes. The backend revalidates unversioned images and serves page HTML without caching.

The sidebar contains only the compact logo/wordmark and five navigation links. It has no motivational footer, large character, or fake paper graphic.
