# Third-Party Sources and Integration

## Generated personality portraits

The personality picker uses a locally bundled [expression-portrait atlas](web/assets/personality/avatar-faces.png), generated with OpenAI image generation for PATPREF. Fifteen states share a peach-and-sage palette, clear facial features and simple symbols. Each portrait occupies a compact 28px box beside its accessible written checkbox label. The original RGBA atlas is displayed through CSS frames. Dimensions, frame boundaries and SHA-256 are recorded in its [manifest](web/assets/personality/avatar-faces.manifest.json); the [generation prompt](web/assets/personality/avatar-faces.prompt.txt) is retained.

## Additional local illustration assets

The local [character sheet](web/assets/personality/characters.png) contains fifteen generated illustrations in five columns and three rows. Dimensions, generation source and SHA-256 are recorded in its [manifest](web/assets/personality/characters.manifest.json). Original code-native SVG faces and gestures remain recorded in the [facet manifest](web/assets/personality/facets/manifest.json).

## Vendored Lucide assets

The SVG files in `web/assets/personality` come from [Lucide](https://lucide.dev/), pinned to revision `81875c8c42d2320fa5123b37fee3554f4ca2bddc` of [lucide-icons/lucide](https://github.com/lucide-icons/lucide/tree/81875c8c42d2320fa5123b37fee3554f4ca2bddc/icons). The SVG source files are unchanged.

- [Upstream license](https://lucide.dev/license): ISC, with MIT notices for Feather-derived icons.
- Full original notices: [retained LICENSE](web/assets/personality/LICENSE).
- Exact source URLs, byte counts and SHA-256 values: [asset manifest](web/assets/personality/manifest.json).

## piStar and browser runtime

PATPREF uses unchanged piStar drawing classes and the pinned runtime files under web/vendor/pistar.

- Repository: [jhcp/piStar](https://github.com/jhcp/piStar).
- Revision: 974d729ee9cbc193c93c403490ab2de471f591f0.
- piStar copyright: 2017 Joao Pimentel.
- piStar license: MIT; the original [LICENSE](web/vendor/pistar/LICENSE) is retained.
- Actual integration: default shape bases, iStar actor/element/link classes, JointJS diagram runtime and its pinned dependencies. PATPREF supplies diagram adapters, layout, contextualization annotations and the compact interface.

| Dependency | Vendored version | License / retained notice |
|---|---|---|
| JointJS | 3.4.4 | [Mozilla Public License 2.0](web/vendor/pistar/LICENSES/JointJS-MPL-2.0.txt), including client IO copyright. |
| jQuery | 3.3.1 | [MIT](web/vendor/pistar/LICENSES/jquery-MIT.txt), JS Foundation and contributors. |
| Lodash | 4.17.21 | [MIT](web/vendor/pistar/LICENSES/lodash-MIT.txt), OpenJS Foundation and contributors; Underscore-derived attribution retained. |
| Backbone.js | 1.4.0 | [MIT](web/vendor/pistar/LICENSES/backbone-MIT.txt), Jeremy Ashkenas / DocumentCloud. |
| Underscore attribution within Lodash | 1.8.3 attribution | [Original MIT notice](web/vendor/pistar/LICENSES/Underscore-MIT.txt). |

Original asset bytes and source headers are preserved. The [manifest](web/vendor/pistar/manifest.json) records exact upstream paths, URLs, byte sizes and SHA-256 values, including license sources.

## SHOP2

- Source: [cl-axon/shop2, original CVS mirror](https://github.com/cl-axon/shop2), cvs/mirror.
- Revision: 8dec6d933be8d1102076aa0ab94d732bdb317e2f.
- Integrated original files: vendor/shop2/shop2.lisp and same-revision state-utils.lisp.
- Original authors: University of Maryland (2002); SIFT, LLC modifications (2004/2005).
- Original notices offer MPL 1.1 / GPL 2.0-or-later / LGPL 2.1-or-later options. Source headers and all three license texts remain in vendor/shop2.

SHOP2 is the planning-system ancestor used by the cited HTNPlan-P approach. PATPREF adds its own transformations, independent validation and contextualization layer. The authors' original transformation scripts and HTNPlan-P preference optimizer have not been obtained.

## Armed Bear Common Lisp

- Runtime: ABCL 1.9.2 on Java.
- Official release: [abcl.org/releases/1.9.2](https://abcl.org/releases/1.9.2/).
- The original jar and COPYING from the same-version official source archive remain in vendor/abcl. COPYING includes GNU GPL terms and the Section 13 linking exception.

The [existing runtime manifest](vendor/manifest.json) records upstream sizes, hashes, URLs, license locations and integration status.

## Model formats and research data

The language and interchange references are documented in [the iStar source review](docs/open_source_istar.md). Format documentation and examples are cited as primary references; unlisted external format-converter code is not part of the vendored runtime.

P10 uses the v43-07 pattern catalogue under `method/materials/`. Its integrity is recorded in `method/release-seal.json`. The example profiles are research personas.
