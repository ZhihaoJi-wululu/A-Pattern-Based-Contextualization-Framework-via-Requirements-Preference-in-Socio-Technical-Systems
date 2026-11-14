# Reading the PATPREF i* Canvas

PATPREF renders imported intentional models with the actual [piStar shape classes](https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/tool/language/shapes.js). The compact arrangement and component proportions follow the supplied goal-model reference: rounded goals, hexagonal tasks, cloud qualities and numbered task badges. The [iStar 2.0 Language Guide](https://arxiv.org/abs/1605.07767) defines the core element meanings. The canvas includes an expandable **Diagram key** beside its reading controls.

## Elements

| Symbol | Meaning |
|---|---|
| Circle — Actor | An entity with goals and intentions. |
| Circle with a curved underline — Role | A responsibility or function an actor can play. |
| Circle with an upper bar — Agent | A concrete actor with an identity. |
| Rounded rectangle — Goal | A state or outcome to achieve. |
| Hexagon with an upper-left numbered badge — Task | An activity or a way to achieve a goal. The badge shows its stable task reference. |
| Rectangle — Resource | Information or a physical entity that is needed or provided. |
| Cloud — Quality | A desired quality whose satisfaction is judged against relevant criteria. |
| Dashed boundary — Actor or role scope | Groups the intentional elements owned by that actor or role. The named symbol is centered just above its boundary. |

The role symbol sits just outside its scope, and the persona symbol is placed beside the assigned role. Owned elements stay inside their own boundary and actor scopes remain separate. Each branch places its parent above its tasks, with sibling alternatives adjacent on one horizontal row. Larger hierarchies use a compact grid of branch groups. Quality clouds sit above or beside the branches they evaluate. Original and Contextualized use the same positions.

A scope expands when the input actor owns internal elements. An actor with no owned goals, tasks, resources or qualities appears as its named actor or role symbol. Select it to read the input's ownership information. The role and its relationships remain part of the model. This presentation follows source ownership in both model views. In the Multiple roles example, Service Auditor has no internal elements and appears as a role symbol.

Names appear within their corresponding symbols. Each task shows its stable reference, t1 through tn, in a small circular badge at its upper-left corner. These references identify tasks; a temporal relation expresses their order. The badge remains attached to the same task in both model views and the SVG export.

## Relationships

**AND refinement** connects the required children to their parent. AND itself is unordered. An optional child retains its optional status. **OR refinement** represents alternative ways to satisfy the parent. Each refinement points from child to parent and carries its piStar endpoint marker and its own AND or OR label. The complete declared Goal/Task refinement structure remains visible, including links to the overall goal.

PATPREF's executable source profile can declare cross-actor decompositions and single-child AND wrappers. The viewer retains those source relations as execution-model extensions. The core iStar 2.0 profile uses actor-local intentional links and requires at least two children for AND, while allowing a single-child OR. See Section 6.1 and the integrity rules in the [language guide](https://arxiv.org/html/1605.07767v3). Source JSON retains the declared ownership, kind and endpoints.

**Start conditions** retain the imported hard constraints. A pre relation requires the source to be attained before the target starts. An npr relation requires the source not to be attained when the target starts; later attainment can remain possible. A separate small open circle at the upper right identifies an optional element.

**Quality / softgoal** uses the original piStar cloud-shaped path with a white fill and dark outline. Quality is the iStar 2.0 core term for the attribute; legacy softgoal and supported precise-quality inputs use the same cloud symbol, as described in Section 4 of the [language guide](https://arxiv.org/pdf/1605.07767).

**Contribution** connects an element to a quality. The labels make (++), help (+), hurt (−) and break (−−) distinguish the source relation's effect. Dashed paths follow the supplied reference's presentation convention. Imported contribution semantics remain part of the source model.

**Dependency** connects a depender, dependum and dependee. The depender relies on the dependee for the goal, task, resource or quality represented by the dependum. The D marker distinguishes this from refinement.

**play** is PATPREF's direct Persona-to-Role assignment. It binds the persona to the selected role. A model can contain several roles while the persona plays one selected role.

The canvas uses this focused preference-modeling relation profile. Imported source records remain traceable in exported JSON.

**preferred_to** labels a contextualized choice preference. Its thicker berry-colored curve, larger open arrow and bold label on a pale rounded backplate distinguish the accepted preference from the source links. Preference labels receive placement priority and their padded dimensions participate in collision checks. Its source alternative is preferred to its target alternative. The complete endpoints and supporting details are available by selecting the relation. Machine-readable preference data retains its canonical identifiers. Choice endpoints are the original direct children of the same OR. A goal endpoint denotes its complete existing implementation subtree; it does not assign a numerical goal weight. Optional participation names its original optional node or scope and requires support across that scope's admitted realizations.

**Temporal preferences** show their concrete relationship, such as precedes, with consistent t1…tn endpoint references. An outline on an existing element indicates a unary participation preference, such as sometime t6. Select the element to read its condition.

## Inspection and navigation

Click a shape or line to read its type, ownership and relevant properties in the detail panel directly above the canvas. Selecting a line emphasizes it and its endpoints while fading unrelated links; closing the details restores the full drawing. The **Diagram key** explains the symbols without opening another workflow.

Connections use smooth cubic curves with continuous tangents through their guide points. Their handles adapt to available space to keep the paths clear of elements and drawing boundaries. Click a line to reveal its curve control point, then drag the point to adjust the curve's position. Its label follows the route. Use **Reset curve** in the selected line's properties to restore the initial route. Adjustments remain available for the same source graph when switching between Original and Contextualized or reloading the page. They change the drawing while preserving the relationship's meaning and endpoints. SVG export retains the adjusted curves and leaves out the editing controls.

New diagrams open at a readable scale and focus the active actor when the full model exceeds the viewport. Scroll horizontally to follow a long row. Use **+**, **−** and **Fit** to change scale; Fit shows the complete overview. Scroll within the canvas for a large model. **Original** and **Contextualized** retain the source graph while showing the chosen view. JSON and SVG exports preserve traceability and the rendered model respectively.
