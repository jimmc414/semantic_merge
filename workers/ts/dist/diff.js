export function diffNodes(base, side) {
    const baseMap = new Map(base.map((n) => [n.symbolId, n]));
    const sideMap = new Map(side.map((n) => [n.symbolId, n]));
    const diffs = [];
    for (const [sid, bnode] of baseMap) {
        const snode = sideMap.get(sid);
        if (!snode) {
            diffs.push({ kind: "delete", a: bnode });
            continue;
        }
        if (bnode.addressId !== snode.addressId) {
            diffs.push({ kind: "move", a: bnode, b: snode });
        }
        if (bnode.name && snode.name && bnode.name !== snode.name) {
            diffs.push({ kind: "rename", a: bnode, b: snode });
        }
    }
    for (const snode of side) {
        if (!baseMap.has(snode.symbolId)) {
            diffs.push({ kind: "add", b: snode });
        }
    }
    return diffs;
}
