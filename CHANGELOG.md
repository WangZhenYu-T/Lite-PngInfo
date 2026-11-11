# Changelog

## v3

- Look up checkpoint and LoRA hashes on Civitai from inside the application, with verified matches linking to the exact model version.
- Query individual models or batches with up to three concurrent requests, duplicate-hash handling and retry controls.
- Distinguish missing or invalid hashes, unverified results, not-found responses, network failures, access restrictions and rate limits.
- Inventory recognized checkpoint, LoRA and diffusion-model references across ComfyUI prompt graphs, editor workflows and serialized subgraphs. Include inactive nodes and preserve node origins without claiming the models were used in the image.
- Reparse older favorites on demand, preserving original images, IDs and creation dates. Create a separate `favorites.before-v3.sqlite3` backup before writing upgraded results.
- Adopt BunnyInfo branding, Alice artwork for the application/browser icons, and a Chinese-first bilingual guide. Historical v1/v2 packages retain their original names.
- Improve proxy detection and startup from Windows/WSL source directories without moving the favorites database.

## v2

- Add NAI, A1111 and Forge categorized metadata, recorded model/LoRA names and hashes, and NAI character prompts.
- Extract ComfyUI prompts from simple, unambiguous paths; preserve complex graph data in the JSON field browser.
- Preserve ordered PNG text entries, duplicate keys, compressed text and text after image data.
- Add per-field JSON formatting, original-text copying, ordered exports and exact large integer seeds.
- Show explicit empty, unknown and partially parsed states. Valid PNGs without generation metadata can still be previewed and saved.
- Add source labels in favorites and on-demand v1 favorite updates, with a SQLite backup before write-back.
- Keep new-image and reset results consistent during rapid file changes.
- Provide ready-to-run Windows x64 packages with a bundled runtime, automatic browser launch and a launcher window for exiting the app.

## v1

- Local PNG metadata viewer with categorized and JSON views.
- NAI prompt and generation-setting extraction.
- Image preview, copying, reset and SQLite favorites containing original PNGs.
- Python source launchers for Windows, Linux and macOS.
