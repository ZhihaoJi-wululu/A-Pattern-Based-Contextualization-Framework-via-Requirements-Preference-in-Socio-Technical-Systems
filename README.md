# PATPREF Contextualization Workbench

PATPREF adds evidence-backed preference requirements to an existing iStar goal model. It uses a persona, a pattern catalogue, and a goal model to identify preferences between complete alternatives under the same original OR refinement. The workbench shows the original and contextualized models and exports JSON, SVG, and PNG.

## Quick start

Use Python 3.11 or later and a modern browser. From this directory, run:

```sh
python run.py --port 8765
```

Open the [local workbench](http://127.0.0.1:8765/). Choose **Confidential directory exchange** under **Examples**, or import a PATPREF JSON, piStar JSON, or supported iStar XML model. Use **Original** to inspect the business model and export the diagram. The server and browser assets are bundled. These steps run locally with the Python standard library.

## Verify the complete workflow locally

```sh
python smoke_test.py
```

The check starts a temporary workbench and a loopback test provider. It imports the directory model, submits a deterministic example through the P10 generation and checking stages, verifies that the expected `preferred_to` relationship passes the mechanical checks, and exports the result. It requires no credentials or internet connection. The fixed response exercises the application pipeline.

## Contextualize with your model provider

1. Copy `.env.example` to `.env.local`. Set `PATPREF_API_BASE_URL` to the provider's base URL up to `/v1` or its equivalent, `PATPREF_API_MODEL` to the model identifier, and `PATPREF_API_KEY` to your credential. The adapter appends `/chat/completions`. Use an HTTPS provider URL or a loopback HTTP endpoint. The provider must support OpenAI-compatible chat completions with strict `json_schema` responses. Environment variables can supply the same settings and take precedence over the file.
2. Load an example or import a goal model. Select its decision-making role and relevant facets, then enter a description of the persona's usual traits.
3. Select **Contextualize model**. Review accepted preferences and their evidence in **Contextualized**. Download the JSON result or export the current diagram as SVG or PNG.

The contextualization step sends the persona, goal model, and relevant pattern rules to the configured provider. Local workspaces and run evidence are written under `data/workspaces/` and `data/runs/p10/`. Use **Original** to export an input diagram without calling a provider. The optional SHOP2 planning API also requires Java on `PATH`.

## Implementation and evidence

- [`apate/`](apate/) implements import, workspace management, the local server, and model export.
- [`web/`](web/) implements the browser interface and iStar diagrams.
- [`method/`](method/) contains the P10 worker, its original generator and checker prompts, the v43-07 catalogue, and the release seal. The release uses local provider settings and its own integrity manifest. The executable pattern catalogue and P10 prompts retain their study versions. Provider and model choice can affect live output.
- [`examples/`](examples/) contains importable models. The separate paper supplement contains the expert instruments and the archived model figures.

See [supported imports](docs/model_import_notes.md), [diagram notation](docs/diagram_notation.md), [the final-model contract](docs/final_model_output.md), and [third-party notices](THIRD_PARTY_NOTICES.md).
