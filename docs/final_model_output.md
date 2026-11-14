# Final preference model output

PATPREF uses `apate.output.final.v1` to identify the terminal status of a modeling pass. The supplied persona, pattern catalogue, and original goal model define the inference scope. See the [bundled P10 implementation](../method/) and the [operational workbench](../README.md).

| Result | Status | Model output |
|---|---|---|
| Required processing and validation complete | `complete`, `is_final=true` | Accepted supported relations, or an empty relation set if the applicable checks establish that none can be instantiated |
| Required input, execution, or validation fails | `failed`, `is_final=false` | Failure status and diagnostic evidence |

An eligible relation has type `preferred_to` and kind `choice`. Its endpoints are different direct children of the same original OR decision, and its source is the preferred endpoint. A goal endpoint represents its complete admitted implementation. Accepted relations carry their rule, facet, and original evidence. Equivalent directed relations retain separate supports. Opposing supported directions record the trade-off.

Model export preserves the original business nodes, role ownership, contributions, and hard constraints. Processing records distinguish valid structural empty outcomes, completed semantic assessments, and failures. Publication requires completion of the necessary checks. The workbench applies the `apate.output.choice.v1` display projection. See the [output projection](output_projection.md) and [diagram interchange](diagram_interchange.md) for representation details.

The paper supplement provides the RQ1 explanation units, the RQ2 complete models, and the RQ3 scale model pairs.

