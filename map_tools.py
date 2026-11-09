"""Inspect trusted local map files from the command line."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from goldsrc_bsp import BSP30
from lta_tree import Node, parse


def lta_summary(path):
    if path.stat().st_size > 32_000_000:
        raise ValueError("LTA file exceeds the 32 MB inspection limit")
    tree = parse(path.read_text(encoding="utf-8-sig"))
    counts = Counter()
    pending = [tree]
    while pending:
        node = pending.pop()
        if node.head:
            counts[node.head] += 1
        pending.extend(item for item in node.items if isinstance(item, Node))
    return {"roots": [node.head for node in tree.items], "nodeTypes": dict(counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("bsp", "Describe a GoldSrc BSP30 map"),
                            ("lta", "Count named nodes in a LithTech ASCII file")):
        commands.add_parser(name, help=help_text).add_argument("input", type=Path)
    wad = commands.add_parser("texture", help="Export one named WAD3 texture to PNG")
    wad.add_argument("input", type=Path)
    wad.add_argument("name")
    wad.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "bsp":
            if args.input.stat().st_size > 8_000_000:
                raise ValueError("BSP file exceeds the 8 MB inspection limit")
            result = BSP30(args.input).summary()
        elif args.command == "lta":
            result = lta_summary(args.input)
        else:
            from goldsrc_wad import textures
            if args.input.stat().st_size > 48_000_000:
                raise ValueError("WAD file exceeds the 48 MB inspection limit")
            name = args.name.lower()
            decoded = textures(args.input, {name})
            if name not in decoded:
                raise ValueError(f"Texture {name!r} was not found in this WAD")
            image = decoded[name]
            with args.output.open("xb") as dest:
                image.save(dest, format="PNG")
            result = {"texture": name, "width": image.width, "height": image.height}
        print(json.dumps(result, indent=2, ensure_ascii=True))
    except (OSError, ValueError, IndexError, struct.error, ImportError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")


if __name__ == "__main__":
    main()
