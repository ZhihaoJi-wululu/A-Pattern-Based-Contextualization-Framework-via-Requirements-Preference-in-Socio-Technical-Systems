# Open-Source iStar and Interchange Review

Reviewed: 2026-10-29. Primary sources were checked directly.

## Core-language reference

The [iStar Language site](https://sites.google.com/site/istarlanguage/) identifies the iStar 2.0 Language Guide by Dalpiaz, Franch and Horkoff; the [authors' publication](https://arxiv.org/abs/1605.07767) introduces that core language. The reviewed sources do not establish a separately released 2026 core standard. Research extensions retain their own names and semantics.

The paper-based PATPREF temporal/execution profile remains an explicitly documented extension and formalization layer over the imported graph.

## Selected implementation

[piStar](https://github.com/jhcp/piStar) is a browser-based iStar editor with source-defined Actor, Agent, Role, Goal, Task, Resource, Quality and typed-link classes. Its [development guide](https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/docs/README.md) separates the existing drawing runtime and language classes from application UI code.

The checked upstream HEAD is 974d729ee9cbc193c93c403490ab2de471f591f0. Its [commit](https://github.com/jhcp/piStar/commit/974d729ee9cbc193c93c403490ab2de471f591f0) is dated 2026-06-14 and updates the research bibliography. The [changelog](https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/CHANGELOG.md) identifies the tool release as v2.1.0 (2021-11-29). A repository update and a language-standard release are distinct facts.

PATPREF vendors these existing components unchanged:

| Component | Source path | Role |
|---|---|---|
| Default shape bases | tool/app/istarcore/defaultShapes.js | Shared piStar drawing bases. |
| iStar classes | tool/language/shapes.js | Actual actor, intentional-element and link shapes. |
| JointJS 3.4.4 | tool/app/istarcore/lib/joint.min.js and joint.min.css | Diagram model, views and SVG rendering. |
| jQuery 3.3.1 | tool/app/istarcore/lib/jquery.min.js | Pinned upstream runtime dependency. |
| Lodash 4.17.21 | tool/app/istarcore/lib/lodash.min.js | Pinned upstream runtime dependency. |
| Backbone 1.4.0 | tool/app/istarcore/lib/backbone-min.js | Pinned upstream runtime dependency. |

The local [manifest](../web/vendor/pistar/manifest.json) records upstream paths, URLs, byte sizes and SHA-256 values. piStar's MIT license and each runtime dependency's notices remain under web/vendor/pistar. JointJS uses MPL 2.0; the other listed runtime dependencies use MIT terms. PATPREF uses these classes in its own viewer and does not describe its application-specific overlays as new iStar core constructs.

## Verified formats

The [piStar serializer](https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/tool/app/istarcore/fileManager.js) saves JSON with actors, orphans, dependencies, links, display, tool, istar, saveDate and diagram fields. Owned nodes are nested within actors. Dependencies contain the dependum and explicit endpoint references; their two connector records occur in links. Refinement links run from child to parent.

The [official iStarML site](https://www.upc.edu/gessi/tools/istar/tools/istarml/index.html) identifies iStarML 1.0 as an XML interchange format for i* variants. The [reference guide](https://www.upc.edu/gessi/tools/istar/tools/istarml/istarmlRefGuide.pdf) defines the tags and references. Relevant source examples are [Test1](https://github.com/UPC-gessi-oscar-franco/iStarJson/blob/master/Test1.istarml) and [Test2](https://github.com/UPC-gessi-oscar-franco/iStarJson/blob/master/Test2.istarml).

The supported XML profile is source-specific: an istarml root with a diagram, actors and boundaries, ielement intentional elements, typed ielementLink records, and dependency endpoints using actor/element references. Source decomposition direction differs from piStar serialization and is mapped explicitly. Unsupported variants and meanings produce findings. Arbitrary XML or XMI is not accepted merely because it is XML.

Visualization and executable projection have separate compatibility boundaries. A graph with multiple business roots or a source-only relation can still be a useful visualization; complete execution reasoning requires the documented PATPREF profile.

## Alternatives reviewed

| Project | Primary evidence | Assessment for this prototype |
|---|---|---|
| BloomingLeaf | [Repository](https://github.com/amgrubb/BloomingLeaf), Apache 2.0; README describes version 2.7 and dynamic intentions with Tropos-based semantics. | Useful research tool, but adopting its analysis formalism would expand this prototype's scope. |
| LAS2peer iStarML Visualizer | [Repository](https://github.com/rwth-acis/las2peer-istarmlvisualizer-service), BSD-style license; XML-to-SVG Java service. | A source reference for XML visualization rather than the selected in-browser component. |
| iStarJson | [Repository](https://github.com/UPC-gessi-oscar-franco/iStarJson), iStarML-to-JSON transformer and source examples. | Interchange examples were inspected; this project's source code is not vendored. |
| istar2fm | [Repository](https://github.com/jmhorcas/istar2fm), GPL 3.0; piStar parser and Ecore/XMI feature-model transformations. | Useful format evidence, but feature-model conversion is outside contextualization. |

The selection is an engineering judgment based on a direct iStar 2.0 browser renderer, reusable classes, explicit interchange code and a small local integration.
