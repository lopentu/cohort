"""Guards on the frontend stylesheet that a human cannot check by reading it.

These are cheap text assertions, not a rendering test — but they cover the two
mistakes this sheet is actually prone to, both of which are invisible until
someone switches theme:

1. The light palette is written **twice** — once under
   `@media (prefers-color-scheme: light)` for "system", once under
   `:root[data-theme="light"]` for an explicit choice. CSS cannot share a
   declaration list between a media query and a plain selector, and adding a
   preprocessor would be a build step this project does not otherwise need. So
   the duplication is deliberate, and this test is what keeps the two copies
   honest.

2. A hardcoded `rgba(255,255,255,…)` surface reads as white-on-white the moment
   the theme flips. Every overlay must go through the `--fill-*` ladder or a
   named surface token.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS_PATH = (
    Path(__file__).parent.parent / "cohort" / "ui" / "frontend" / "src" / "styles.css"
)

pytestmark = pytest.mark.skipif(
    not CSS_PATH.is_file(), reason="frontend sources not present"
)


@pytest.fixture(scope="module")
def css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _tokens(block: str) -> dict[str, str]:
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[\w-]+):\s*([^;]+);", block)
    }


def _root_block(css: str) -> str:
    m = re.search(r"\n:root \{(.*?)\n\}", css, re.S)
    assert m, "no bare :root block"
    return m.group(1)


def _light_media_block(css: str) -> str:
    m = re.search(
        r'@media \(prefers-color-scheme: light\) \{\s*'
        r':root:not\(\[data-theme="dark"\]\) \{(.*?)\n  \}\n\}',
        css, re.S,
    )
    assert m, "no prefers-color-scheme: light block"
    return m.group(1)


def _light_attr_block(css: str) -> str:
    m = re.search(r':root\[data-theme="light"\] \{(.*?)\n\}', css, re.S)
    assert m, "no :root[data-theme=light] block"
    return m.group(1)


def test_the_two_light_palettes_have_not_drifted(css):
    """The system-light and explicitly-light palettes must be identical. If
    they diverge, one of the two theme paths quietly gets different colours."""
    from_media = _tokens(_light_media_block(css))
    from_attr = _tokens(_light_attr_block(css))
    assert from_media, "light media block defines no tokens"
    assert from_media == from_attr, (
        "the two light palettes have drifted:\n"
        f"  only in media query: {sorted(set(from_media) - set(from_attr))}\n"
        f"  only in [data-theme]: {sorted(set(from_attr) - set(from_media))}\n"
        "  differing values: "
        + str({
            k: (from_media[k], from_attr[k])
            for k in set(from_media) & set(from_attr)
            if from_media[k] != from_attr[k]
        })
    )


def test_every_light_token_has_a_dark_default(css):
    """Dark is the base on `:root`. A token defined only in a light block would
    be undefined whenever the theme is dark, and `var()` with no fallback
    resolves to nothing — a silently missing colour."""
    dark = _tokens(_root_block(css))
    light = _tokens(_light_attr_block(css))
    missing = sorted(set(light) - set(dark))
    assert not missing, f"defined for light but not for dark: {missing}"


def test_no_hardcoded_white_overlays_outside_the_palette(css):
    """Overlays must come from the `--fill-*` ladder so they invert with the
    theme. Inside the token blocks they are the definitions themselves; in the
    body of the sheet they are a light-mode bug."""
    _, sep, body = css.partition("* { box-sizing: border-box; }")
    assert sep, "could not locate the end of the token blocks"
    offenders = re.findall(r"[^\n;{]*rgba\(\s*255,\s*255,\s*255[^\n;]*", body)
    assert not offenders, "hardcoded white overlays in the sheet body:\n" + "\n".join(
        o.strip() for o in offenders[:10]
    )


def test_theme_is_switchable_in_all_three_states(css):
    """`system` stamps no attribute; light and dark each need a selector that
    beats the media query, or an explicit choice would lose to the OS."""
    assert 'prefers-color-scheme: light' in css
    assert ':root[data-theme="light"]' in css
    assert ':root:not([data-theme="dark"])' in css, (
        "the media query must exclude an explicit dark choice, or picking dark "
        "on a light-preferring OS would be overridden"
    )


def test_discounting_edges_stay_distinguishable_without_hue(css):
    """docs/design.md §10: a restyle must not reduce `parallel_of`/`descends_from`
    to a colour difference. They carry the argument that agreement between
    related witnesses is not independent confirmation, so they must also differ
    in dash pattern and weight — which survives a theme switch and colour
    blindness alike."""
    # anchored to line start so this matches the SVG rule, not `.swatch.e-discount`
    m = re.search(r"^\.e-discount \{([^}]*)\}", css, re.M)
    assert m, "no .e-discount rule for graph edges"
    rule = m.group(1)
    assert "stroke-dasharray" in rule, "discounting edges lost their dash pattern"
    assert "stroke-width" in rule, "discounting edges lost their distinct weight"

    contradicts = re.search(r"^\.e-contradicts \{([^}]*)\}", css, re.M)
    assert contradicts and "stroke-width" in contradicts.group(1), (
        "contradiction must stay as heavy as agreement (docs/design.md §10)"
    )

    # the legend has to teach the same distinction, or the graph is a code the
    # reader has not been given
    swatch = re.search(r"\.swatch\.e-discount \{([^}]*)\}", css)
    assert swatch and "dashed" in swatch.group(1), (
        "the legend swatch for discounting edges must be dashed too"
    )


def test_node_status_is_not_a_hue_only_channel(css):
    """§10 requires status to be a visual channel. It was a coloured bar down
    the node's left edge and is now the node's outline, which is a better place
    for it — but an outline that varies only in colour is a channel a greyscale
    printout and a red-green colourblind reader both lose.

    So the ladder differs in more than hue: `proposed` is dashed because it is
    provisional, `accepted` is heavier because it is the only citable state,
    and `rejected` keeps its struck-through title.
    """
    proposed = re.search(r"^\.s-proposed \.node-box \{([^}]*)\}", css, re.M)
    assert proposed, "no status outline rule for proposed nodes"
    assert "stroke-dasharray" in proposed.group(1), (
        "`proposed` must be distinguishable without colour — nothing has "
        "checked it yet, and a solid outline claims otherwise"
    )

    accepted = re.search(r"^\.s-accepted \.node-box \{([^}]*)\}", css, re.M)
    assert accepted and "stroke-width" in accepted.group(1), (
        "`accepted` is the only citable state and must carry weight, not just hue"
    )

    rejected = re.search(r"^\.s-rejected \.node-title \{([^}]*)\}", css, re.M)
    assert rejected and "line-through" in rejected.group(1), (
        "a rejected node must read as rejected without its outline colour"
    )


def test_selecting_a_node_does_not_repaint_its_status(css):
    """The status outline and the selection indicator are different channels on
    the same shape, so they must not be the same property. Before the outline
    carried status, `.node.selected .node-box` set `stroke` — harmless then,
    and now it would hide a node's status at the moment the reader is looking
    hardest at it."""
    selected = re.search(r"^\.node\.selected \.node-box \{([^}]*)\}", css, re.M)
    if selected:
        assert "stroke" not in selected.group(1), (
            "selection must not restyle the box stroke: that stroke is status. "
            "Use `.node-ring` instead."
        )
    ring = re.search(r"^\.node\.selected \.node-ring \{([^}]*)\}", css, re.M)
    assert ring and "stroke" in ring.group(1), "selection has no visible ring"


def test_the_findings_panel_cannot_be_widened_by_a_long_ref(css):
    """A grid/flex item's default `min-width: auto` refuses to shrink below its
    content, and a canonical ref
    (`A097n1267#Bookcase/CBETA/XML/A/A097/A097n1267_004.xml`) is a single
    unbreakable word. One evidence row was enough to push the whole tab into a
    horizontal scroll.

    Both halves are load-bearing: `min-width: 0` alone lets the box shrink
    while the token spills out of it, and wrapping alone does nothing while the
    grid track is still sized to the token. So both are asserted.
    """
    shrink = re.search(r"^\.hypotheses, \.hyp-list, \.hyp, [^{]*\{([^}]*)\}", css, re.M)
    assert shrink and "min-width: 0" in shrink.group(1), (
        "the hypothesis list and its rows must be allowed to shrink below "
        "their content, or a long ref widens the panel"
    )

    wrap = re.search(r"^\.ev-ref, \.dossier code[^{]*\{([^}]*)\}", css, re.M | re.S)
    assert wrap and "overflow-wrap: anywhere" in wrap.group(1), (
        "refs and node ids in a dossier must be able to break mid-token: "
        "`break-word` alone will not break inside `/` and `::` runs"
    )


def test_buttons_holding_prose_are_allowed_to_wrap(css):
    """The bug the rule above did not fix. The hypothesis assertion and the
    evidence ref are both `<button>`s — text with a click target around it —
    and the global button rule sets `white-space: nowrap` along with
    `overflow: hidden` and an ellipsis. Those are right for compact controls
    and fatal for prose: `overflow-wrap` has no effect at all while wrapping is
    forbidden, so every wrapping declaration in the panel was inert.

    Asserted separately from the wrapping rules because it is a different
    failure — the wrapping was present and correct and still did nothing.
    """
    base = re.search(r"^button \{([^}]*)\}", css, re.M | re.S)
    assert base and "nowrap" in base.group(1), (
        "this guard assumes the global button rule forbids wrapping; if that "
        "changed, re-check whether the override below is still needed"
    )

    override = re.search(
        r"^\.hyp-head, \.ev-ref[^{]*\{([^}]*)\}", css, re.M | re.S
    )
    assert override, "no wrapping override for the prose-bearing buttons"
    rule = override.group(1)
    for prop in ("white-space: normal", "overflow: visible", "text-overflow: clip"):
        assert prop in rule, (
            f"`{prop}` missing: all three of the global button's clipping "
            "properties have to be undone, or the text still truncates"
        )


def test_the_floating_panels_stay_opaque(css):
    """Node detail, settings and graph contents float over the graph and carry
    small provenance text — ids, refs, verification detail. Translucency was
    tried and removed: it costs legibility over whatever the graph puts behind
    them, in exchange for an effect that barely registered, because the graph
    is mostly flat ground and thin strokes with little back there to blur.

    Asserted so a future pass at "glass" has to argue with this rather than
    rediscover it.
    """
    for sel in (".panel", ".settings-pop", ".stats-pop"):
        rules = re.findall(rf"^{re.escape(sel)} \{{([^}}]*)}}", css, re.M | re.S)
        surfaced = [r for r in rules if "background:" in r]
        assert surfaced, f"no surface rule for {sel}"
        for rule in surfaced:
            assert "backdrop-filter" not in rule, (
                f"{sel} is translucent again — see the comment on `.panel`"
            )
            assert "var(--bg-raised)" in rule, (
                f"{sel} must use the opaque raised surface"
            )


# --- one global sheet, one owner per class name ------------------------------

#: Class names deliberately defined twice, each with a reason. A bare entry is
#: the drift this check exists to catch.
DUPLICATE_CLASSES: dict[str, str] = {
    ".plan-row": (
        "layered on purpose: the first rule is a `min-width: 0` overflow guard "
        "grouped with the other min-width guards, the second is the grid "
        "itself. Neither sets a property the other does."
    ),
    ".verification": (
        "pre-existing collision between the DetailPanel's verification card "
        "and the Findings dossier's. Both are 'a verification card' so the "
        "result is survivable, but the Findings rule wins on margin, padding "
        "and border for both. Recorded rather than fixed: splitting them is a "
        "visual change to the inspector that wants looking at, not a rename."
    ),
}


def test_no_class_is_styled_by_two_unrelated_components(css):
    """One global stylesheet and no CSS modules, so a class name is a shared
    namespace — and a generic one is a collision waiting for whichever
    component is styled second.

    This is not hypothetical. On 2026-09-07 the association chip in Placements
    was named `.verdict`, which was already the researcher-decision `<section>`
    in DetailPanel. The chip's rule — a 999px radius, a filled background and
    `white-space: nowrap` — landed on the whole panel: a giant pill behind the
    Attest/Accept/Reject buttons, with the ladder explanation clipped instead
    of wrapped. It built cleanly, every test passed, and it was found by
    looking at the screen.
    """
    import re
    from collections import defaultdict

    defs: dict[str, list[int]] = defaultdict(list)
    for m in re.finditer(r"^(\.[A-Za-z][\w-]*)\s*\{", css, re.M):
        defs[m.group(1)].append(css[: m.start()].count("\n") + 1)

    unexplained = {
        cls: lines for cls, lines in defs.items()
        if len(lines) > 1 and cls not in DUPLICATE_CLASSES
    }
    assert not unexplained, (
        "these class names are styled by more than one rule block:\n  "
        + "\n  ".join(f"{c} at lines {ls}" for c, ls in sorted(unexplained.items()))
        + "\nOne global sheet means one owner per name. Scope the newer one "
          "(`.assoc-verdict`, not `.verdict`), or record the overlap in "
          "DUPLICATE_CLASSES with the reason it is safe."
    )


def test_every_recorded_duplicate_still_exists():
    """So the allowlist cannot outlive the overlap it excuses."""
    import re

    src = CSS_PATH.read_text(encoding="utf-8")
    for cls in DUPLICATE_CLASSES:
        found = re.findall(rf"^{re.escape(cls)}\s*\{{", src, re.M)
        assert len(found) > 1, (
            f"{cls} is recorded in DUPLICATE_CLASSES but is no longer defined "
            "twice — drop the entry."
        )


def test_each_recorded_duplicate_carries_a_reason():
    blank = sorted(k for k, v in DUPLICATE_CLASSES.items() if not v.strip())
    assert not blank, f"duplicates recorded without a reason: {blank}"


def test_no_table_is_its_own_scroller(css):
    """`display: block` on a `<table>` turns its `thead` and `tbody` into
    ordinary blocks, and the moment they stop being table sections they stop
    sharing column widths — every header ends up over the wrong column.

    It is a tempting rule because it is the shortest way to make a wide table
    scroll, and it is the one way that also stops the thing being a table. The
    scroller belongs on a wrapper.
    """
    import re

    offenders = []
    for m in re.finditer(r"^(\.[\w.-]+(?:\s*,\s*\.[\w.-]+)*)\s*\{([^}]*)\}", css, re.M):
        sel, body = m.group(1), m.group(2)
        if "table" not in sel:
            continue
        if re.search(r"display:\s*block", body) and "overflow" in body:
            offenders.append(f"{sel.strip()} (line {css[: m.start()].count(chr(10)) + 1})")
    assert not offenders, (
        "these table rules make the table its own scroller:\n  "
        + "\n  ".join(offenders)
        + "\nPut `overflow-x: auto` on a wrapper and leave the table a table."
    )

