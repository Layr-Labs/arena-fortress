#!/usr/bin/env python3
"""Writes yukon-automation.csv (quickfort blueprint for the automation arm). Generated so the column arithmetic
stays right: 23 columns, 5 rows (rooms use rows 2-4), the access stair at column 12, row 3 (the start cursor of every level section)."""
import os

W, S = 23, 12


def grid(cells, rows=5):
    g = [[""] * W for _ in range(rows)]
    for (r, c), v in cells.items():
        g[r - 1][c - 1] = v
    return "\n".join(",".join(row) for row in g)


def main():
    out = ['#notes label(help) yukon automation arm: a small fort for the default start (research/automation-arm.md)\n'
           '"Every level section uses the access stair as its start cursor. automation.lua stair_site picks it:"\n'
           '"open surface floor whose footprint on the three soil levels below is dry non-aquifer soil."\n'
           '"/stair_top on the surface; /farm_dig one level down; /rooms_dig two down; /dorm2_dig three down."\n'
           '"Once a level is dug: /farm_build; quickfort orders + run /rooms_build then /rooms_zone; same for dorm2."\n'
           '"/still and /kitchen take a workshop centre as the cursor."']

    def sec(header, cells):
        out.append(header + "\n" + grid(cells))

    start = "start(12;3;access stair)"
    sec(f"#dig label(stair_top) {start} down stair on the surface", {(3, S): "j"})
    sec(f"#dig label(farm_dig) {start} up-down stair and an 11x3 farm room to its east",
        {(3, S): "i", (2, 13): "d(11x3)"})
    sec(f"#dig label(rooms_dig) {start} up-down stair with an 11x3 dormitory east and a 5x3 dining room west",
        {(3, S): "i", (2, 13): "d(11x3)", (2, 7): "d(5x3)"})
    sec(f"#dig label(dorm2_dig) {start} up stair and a second 11x3 dormitory east", {(3, S): "u", (2, 13): "d(11x3)"})
    sec(f"#build label(farm_build) {start} three 3x3 farm plots",
        {(2, 13): "p(3x3)", (2, 17): "p(3x3)", (2, 21): "p(3x3)"})
    beds = {(r, c): "b" for r in (2, 4) for c in range(13, 24)}      # middle row is the walkway from the stair
    dining = {(2, c): "t" for c in (7, 9, 11)}
    dining.update({(3, c): "c" for c in (7, 9, 11)})
    sec(f"#build label(rooms_build) {start} 22 dormitory beds plus 3 tables and 3 chairs in the dining room",
        {**beds, **dining})
    sec(f"#zone label(rooms_zone) {start} dormitory and dining hall zones", {(2, 13): "D(11x3)", (2, 7): "h(5x3)"})
    sec(f"#build label(dorm2_build) {start} 22 more beds", beds)
    sec(f"#zone label(dorm2_zone) {start} second dormitory zone", {(2, 13): "D(11x3)"})
    for name, code in (("still", "wl"), ("kitchen", "wz")):
        out.append(f"#build label({name}) start(2;2;workshop centre) one 3x3 workshop\n`,`,`\n`,{code},`\n`,`,`")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "yukon-automation.csv"), "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
