# Changelog

## v2

- NAI, A1111, and Forge categorized metadata, recorded model/LoRA names and hashes, and NAI v4 character prompts.
- Minimal ComfyUI classification: only prompts from a simple, unambiguous path; complex graph data remains in the JSON field browser.
- Ordered PNG text entries, including duplicate keys, tEXt/zTXt/iTXt, and text after image data.
- Per-field JSON formatting and original-text copying, ordered field export, and exact large integer seeds.
- Explicit empty/unknown/partially parsed metadata states; valid metadata-free PNGs can still be previewed and favorited.
- Source labels in favorites; on-demand v1 favorite reparse with a one-time SQLite backup before write-back.
- Clear previous results when choosing/reading a new image; serialize browser session writes so reset and fast file changes remain consistent.
- Remove duplicated raw/png_text payloads and avoid fetching image BLOBs for the favorites summary list.

## v1

- Local PNG metadata WebUI with categorized and JSON views.
- NovelAI prompt and generation parameter extraction.
- Optional preview, copy, reset, and SQLite favorites.
- Linux/macOS shell launcher, native Windows BAT, and personal WSL launchers.
- Isolated HTTP regression tests and Windows/Linux CI.
