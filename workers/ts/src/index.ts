import readline from "node:readline";
import { BuildAndDiffParams, BuildAndDiffResult } from "./protocol.js";
import { parseFiles, buildIndex } from "./sast.js";
import { diffNodes } from "./diff.js";
import { lift } from "./lift.js";

type RpcRequest = { jsonrpc: "2.0"; id: number; method: string; params: any };

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

async function main() {
  for await (const line of rl) {
    if (!line) continue;
    const req = JSON.parse(line) as RpcRequest;
    try {
      if (req.method === "buildAndDiff") {
        const params = req.params as BuildAndDiffParams;
        const baseProg = parseFiles(params.base.files);
        const leftProg = parseFiles(params.left.files);
        const rightProg = parseFiles(params.right.files);

        const baseIdx = buildIndex(baseProg);
        const leftIdx = buildIndex(leftProg);
        const rightIdx = buildIndex(rightProg);

        const diffA = diffNodes(baseIdx.nodes, leftIdx.nodes);
        const diffB = diffNodes(baseIdx.nodes, rightIdx.nodes);

        const result: BuildAndDiffResult = {
          opLogLeft: lift("base", diffA),
          opLogRight: lift("base", diffB),
          symbolMaps: {
            base: baseIdx.nodes.map((n) => ({ symbolId: n.symbolId, addressId: n.addressId })),
            left: leftIdx.nodes.map((n) => ({ symbolId: n.symbolId, addressId: n.addressId })),
            right: rightIdx.nodes.map((n) => ({ symbolId: n.symbolId, addressId: n.addressId })),
          },
          diagnostics: [],
        };
        respond(req.id, result);
      } else if (req.method === "diff") {
        const baseProg = parseFiles(req.params.base.files);
        const rightProg = parseFiles(req.params.right.files);
        const diff = diffNodes(buildIndex(baseProg).nodes, buildIndex(rightProg).nodes);
        respond(req.id, { opLogRight: lift("base", diff) });
      } else {
        error(req.id, -32601, "Method not found");
      }
    } catch (err: any) {
      error(req.id, -32000, err?.message ?? String(err));
    }
  }
}

function respond(id: number, result: any) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}

function error(id: number, code: number, message: string) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n");
}

main();
