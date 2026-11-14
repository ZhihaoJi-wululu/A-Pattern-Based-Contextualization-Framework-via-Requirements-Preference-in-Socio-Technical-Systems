# Manual Input and UI Parity Guide

**Contextualize model** applies the frozen P10 method to the supplied persona, v43-07 pattern catalogue and existing goal model. P10 generates and checks each selected facet, mechanically validates the proposed original OR choices and merges supported directions.

## Start the service

Run the command from the workbench directory.

```text
python run.py --port 8765
```

Open the [local workbench](http://127.0.0.1:8765/). The service reads the provider settings from `.env.local` or the environment.

## Enter a model and persona

1. Use **Choose model file** to import JSON or supported iStarML XML. Inspect the imported graph in **Original**.
2. Enter the person's name, select the active role under **Acts as**, and select the facets supported by the persona.
3. Enter the person's usual characteristics and behavior in **Persona description**.
4. Click **Contextualize model**. Inspect the final supported preference model in **Contextualized**. Select elements or relations for details and open **Diagram key** for notation.
5. Download research JSON and export the drawing as SVG.

Keep the supplied persona description fixed when reproducing a run. P10 compares direct children of the same original OR and checks complete implementations against the model's constraints. A facet with a verified empty choice rule set completes through a local certificate and recomputation. A successful run returns all supported final relations, which can be empty. The [final-model contract](final_model_output.md) distinguishes a completed result from an input or processing failure.

The public request contains `persona` and the current workspace `revision`. Editing the persona invalidates the displayed result, and a late response from an older input is discarded. Task aliases t1…tn identify source elements without assigning temporal order.

## Import the paper example

Import the directory-exchange example to inspect the goal model and its supplied persona in the workbench. Check the active role, selected facets and description before running contextualization. [Example JSON](../examples/directory_exchange.json)

The paper supplement provides the expert instruments and the archived figures for the main and scale studies.

## Model inspection

**Original** and **Contextualized** share source identities and business structure. **plays** identifies the active persona-to-role assignment while all source roles remain visible. **Fit**, **Auto layout** and draggable curve controls affect presentation. JSON exports retain source mappings, complete validated preferences and available research provenance; SVG exports retain the visible model geometry.
