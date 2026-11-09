# Wolfory map tools

Three standalone Python tools extracted from the Wolfory map-authoring workflow. They read mapper-supplied files offline. Python 3.10 or later is recommended. The BSP and LTA commands use the standard library. The texture command requires Pillow.

## Inspect a LithTech ASCII scene

```sh
python map_tools.py lta example.lta
```

The included example has three `worldnode` entries. The report counts named list heads and identifies the top-level roots. Authors writing their own analysis can use `lta_tree.parse`, `walk`, and `raw` to retain source spans. Input is UTF-8 or ASCII.

## Inspect a GoldSrc BSP30 level

```sh
python map_tools.py bsp your-map.bsp
```

The JSON report contains the world bounds, texture names, entity class counts, brush-model entities and player starts found in the file. It also includes geometry counts and a SHA-256 digest. You can redirect stdout to save the report. The library exposes face polygons and convex solid cells for authors doing geometry analysis.

## Export a named WAD3 texture

Use one of the texture names listed by the BSP report and the corresponding local WAD3. Texture names are case-insensitive.

```sh
python -m pip install Pillow
python map_tools.py texture -- your-textures.wad brick01 brick01.png
```

The decoder reads uncompressed paletted WAD3 miptextures. A texture whose name starts with `{` uses palette index 255 for transparency. Choose a new output filename for each export.

This is the standalone reader subset of the internal map studio. The native map compiler, editor UI and game content are outside this package.
