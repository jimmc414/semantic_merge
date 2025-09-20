import crypto from "node:crypto";
function newId() {
    return crypto.randomUUID();
}
const now = () => new Date().toISOString();
export function lift(baseRev, diffs) {
    const ops = [];
    for (const diff of diffs) {
        if (diff.kind === "rename" && diff.a && diff.b) {
            ops.push({
                id: newId(),
                schemaVersion: 1,
                type: "renameSymbol",
                target: { symbolId: diff.a.symbolId, addressId: diff.a.addressId },
                params: { oldName: diff.a.name, newName: diff.b.name, file: diff.b.range.file },
                guards: { exists: true, addressMatch: diff.a.addressId },
                effects: { summary: `rename ${diff.a.name}→${diff.b.name}` },
                provenance: { rev: baseRev, timestamp: now() },
            });
        }
        else if (diff.kind === "move" && diff.a && diff.b) {
            ops.push({
                id: newId(),
                schemaVersion: 1,
                type: "moveDecl",
                target: { symbolId: diff.a.symbolId, addressId: diff.a.addressId },
                params: {
                    oldAddress: diff.a.addressId,
                    newAddress: diff.b.addressId,
                    oldFile: diff.a.range.file,
                    newFile: diff.b.range.file,
                },
                guards: { exists: true, addressMatch: diff.a.addressId },
                effects: { summary: `move ${diff.a.addressId}→${diff.b.addressId}` },
                provenance: { rev: baseRev, timestamp: now() },
            });
        }
        else if (diff.kind === "add" && diff.b) {
            ops.push({
                id: newId(),
                schemaVersion: 1,
                type: "addDecl",
                target: { symbolId: diff.b.symbolId, addressId: diff.b.addressId },
                params: { file: diff.b.range.file },
                guards: {},
                effects: { summary: "add decl" },
                provenance: { rev: baseRev, timestamp: now() },
            });
        }
        else if (diff.kind === "delete" && diff.a) {
            ops.push({
                id: newId(),
                schemaVersion: 1,
                type: "deleteDecl",
                target: { symbolId: diff.a.symbolId, addressId: diff.a.addressId },
                params: { file: diff.a.range.file },
                guards: {},
                effects: { summary: "delete decl" },
                provenance: { rev: baseRev, timestamp: now() },
            });
        }
    }
    return ops;
}
