# Existing Goal Model Import

The importer accepts an PATPREF Goal Model object, an `{M0: ...}` wrapper, an PATPREF research session, or a `{session: ...}` research wrapper. The supplied business model is validated, required schema defaults are normalized, and actual supplied persona/context/evidence may be retained. Importing alone makes no model-provider request.

Each **Contextualize model** action runs P10 using the current persona, the original goal model's execution projection and the frozen pattern catalogue. Workbench JSON exports carry the original `source_document` and editable `persona`. A completed export also carries its validated analysis and run provenance. Reimport restores the source diagram and persona for a fresh P10 run.

See the [manual input guide](manual_input_guide.md) for raw JSON/XML entry and the bundled directory-exchange example.

## piStar reference

The adapter was checked against the primary [piStar repository](https://github.com/jhcp/piStar), revision `974d729ee9cbc193c93c403490ab2de471f591f0`, particularly [fileManager.js](https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/tool/app/istarcore/fileManager.js) and [metamodel.js](https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/tool/language/metamodel.js).

Its serialized iStar 2.0 document has actors with internal nodes, unowned `orphans`, outside dependums in `dependencies`, and typed `links`. A dependency also has two explicit `istar.DependencyLink` connectors. AND/OR links run from child to parent. The importer groups those source links without changing their operator or children.

## Supported executable fragment

- Actor, Agent and Role; Goal, Task, Quality and Resource.
- One connected goal/task execution tree with leaf tasks and one existing root.
- Complete AND or OR refinement groups. Exactly-one implementation is the current PATPREF execution policy for OR.
- Explicit `make` and `break` contributions mapped to their exact PATPREF effects.
- Declared dependencies with typed external dependums and actor/local-node endpoints.

PiStar diagrams can express a broader language than this prototype's execution checker. Multiple disconnected business roots, shared business subtrees, refined tasks, needed-by/qualification/actor-association links, and `help`/`hurt` effects require an explicit supported execution projection. The importer reports these conditions instead of inventing a root, discarding relations or approximating their effects. Selecting a root never discards other supplied business branches.

Legal source IDs are kept. IDs outside the PATPREF identifier grammar receive stable mapped IDs recorded in `report.id_map`; source documents, source IDs and connector mappings remain in `import_provenance`. Drawing coordinates and custom properties are archived and do not automatically create execution constraints or preference requirements.
