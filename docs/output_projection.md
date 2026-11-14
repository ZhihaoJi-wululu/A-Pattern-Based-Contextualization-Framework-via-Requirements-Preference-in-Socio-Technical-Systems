# Choice model output profile

The desktop workbench uses `apate.output.choice.v1` for its relation display projection. Terminal modeling completion follows the separate [final-model contract](final_model_output.md), `apate.output.final.v1`. `result.preferences` contains validated `choice` relations between existing alternatives. Their semantic relation is `preferred_to`; the diagram uses its concise choice caption.

P10 finalizes the supported original OR choices as `complete`, `is_final=true` after all selected facets complete. Input or processing failures return `failed`, `is_final=false` with diagnostics. Original temporal preferences remain part of the source model.

The imported diagram, business constraints, role ownership, goal decomposition, qualities, contribution effects and execution witnesses remain unchanged. Output projection is separate from the input model and from independent validation.

## Export fields

- `output_profile` identifies the choice display contract.
- `result.preferences` contains the final relations using diagram IDs. The summary counts their relations and supports.
- `internal_result` contains the desktop result before the display projection.
- `analysis_session.result` contains the validated relations with canonical IDs, their literal evidence and matched implementation witnesses.
- `artifacts.input_contract` records the method and input fingerprints. `artifacts.p10_run` identifies the stage archive relative to the workbench's `data/` directory, with the P10 output path relative to that archive.
- `source_document` and `base_session` retain the imported inputs.

Reading or exporting an existing workspace presents the stored result with its recorded method. Contextualizing it again generates a fresh P10 result from the current inputs.
