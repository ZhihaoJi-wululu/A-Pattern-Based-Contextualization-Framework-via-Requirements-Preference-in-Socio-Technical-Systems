# Existing i* diagram interchange

`apate.diagram_io.load_diagram(document, filename=None)` admits a display graph separately from PATPREF's finite execution checker. The return value contains the name, detected format, actors, intentional elements, all source links, task references, original document and a compatibility report. An exact executable session is included only when the existing execution contract accepts the complete supplied structure.

## JSON

The supported JSON inputs are PATPREF Goal Models/research sessions and the public piStar iStar 2.0 serializer format. piStar actors own internal nodes, while outside dependums and explicit dependency connectors remain outside their boundaries. Source IDs, custom properties, coordinates, dimensions and routing vertices remain traceable. Help/hurt, needed-by, qualification, actor associations and explicit unknown link meanings remain in the display graph even when executable reasoning is unavailable.

The piStar reference is [jhcp/piStar](https://github.com/jhcp/piStar), particularly `tool/app/istarcore/fileManager.js` and `tool/language/metamodel.js`, upstream revision `974d729ee9cbc193c93c403490ab2de471f591f0`.

## XML

XML input uses the published [iStarML 1.0 interchange format](https://www.upc.edu/gessi/tools/istar/tools/istarml/index.html). Syntax was checked against the primary [UPC iStarJSON project's interchange examples](https://github.com/UPC-gessi-oscar-franco/iStarJson/blob/master/Test2.istarml). The parser is an independent implementation of the interchange structure.

The file root is `istarml` with version `1.0`, containing one or more diagrams. Actors contain a boundary with goal, task, resource or softgoal definitions. Intentional links may use an existing `iref` or nested child definitions. Refinement links inside a parent point to its children; the normalized display edge runs child-to-parent. A contribution inside its source points to its target. Diagram-level dependums declare depender and dependee actors and optional local intentional endpoints.

Legacy position actors and legacy relation meanings remain explicit source metadata. They receive no approximate executable interpretation. Multiple diagrams with globally unique logical IDs remain in one display graph with `diagram_id` metadata. Repeated IDs, missing references, misplaced semantic elements, referenced actor instances, nested actors and non-binary dependency declarations produce explicit findings or errors rather than omitted structure. DTD/entity declarations are rejected. Embedded SVG is archived in the original document and is never executed as diagram markup.

The official iStarML site identifies its published version as 1.0. This adapter does not relabel the proposed iStarML 2.0 dialect as an established interchange standard.

## Display and reasoning

The full input determines stable `t1` through `tn` task references; dependum tasks are excluded from the execution-task sequence. Existing contiguous source references retain their identity. Native temporal preference declarations remain in `graph.temporal_preferences`, separately from ordinary source links. Their original endpoint identities and formulas remain unchanged.

PATPREF execution admission still requires its explicit finite fragment: one connected business root, leaf tasks and supported effects. A display graph can therefore be valid while `report.reasoning_supported` is false. In that case, `session` is null and `reasoning_findings` explains the exact admission limits. The importer never invents a business root, drops unsupported links, changes a source task's type, or turns partial contribution evidence into an exact effect.
