import ts from "typescript";
import crypto from "node:crypto";

export type NodeInfo = {
  symbolId: string;
  addressId: string;
  kind: string;
  name: string | null;
  range: { file: string; start: number; end: number };
};

type SourceFileInput = { path: string; content: string };

export function parseFiles(files: SourceFileInput[]): ts.Program {
  const options: ts.CompilerOptions = { allowJs: true };
  const host = ts.createCompilerHost(options, true);
  const fileMap = new Map<string, string>(files.map((f) => [normalizePath(f.path), f.content]));

  host.readFile = (fileName) => {
    const norm = normalizePath(fileName);
    return fileMap.get(norm) ?? "";
  };
  host.fileExists = (fileName) => fileMap.has(normalizePath(fileName));
  host.getSourceFile = (fileName, languageVersion) => {
    const norm = normalizePath(fileName);
    const text = fileMap.get(norm);
    if (text === undefined) return undefined;
    return ts.createSourceFile(norm, text, languageVersion, true, ts.ScriptKind.TS);
  };
  host.getCurrentDirectory = () => ".";
  host.getDirectories = () => [];
  host.getCanonicalFileName = (f) => normalizePath(f);
  host.useCaseSensitiveFileNames = () => true;

  const fileNames = files.map((f) => normalizePath(f.path));
  return ts.createProgram({ rootNames: fileNames, options, host });
}

export function buildIndex(prog: ts.Program) {
  const checker = prog.getTypeChecker();
  const nodes: NodeInfo[] = [];
  for (const sf of prog.getSourceFiles()) {
    if (sf.isDeclarationFile) continue;
    ts.forEachChild(sf, function walk(n) {
      if (
        ts.isFunctionDeclaration(n) ||
        ts.isClassDeclaration(n) ||
        ts.isInterfaceDeclaration(n) ||
        ts.isEnumDeclaration(n) ||
        ts.isVariableStatement(n)
      ) {
        const name = (n as any).name?.getText?.() ?? null;
        const kind = ts.SyntaxKind[n.kind];
        const addressId = computeAddressId(sf, n, name);
        const symbolId = computeSymbolId(checker, n);
        const range = { file: sf.fileName, start: n.pos, end: n.end };
        nodes.push({ symbolId, addressId, kind, name, range });
      }
      ts.forEachChild(n, walk);
    });
  }
  return { nodes, checker };
}

function computeAddressId(sf: ts.SourceFile, n: ts.Node, name: string | null): string {
  return `${sf.fileName}::${name ?? "anon"}::${n.pos}`;
}

function hash(data: string): string {
  return crypto.createHash("sha256").update(data).digest("hex").slice(0, 16);
}

export function computeSymbolId(checker: ts.TypeChecker, n: ts.Node): string {
  let sig = "";
  if (ts.isFunctionDeclaration(n) && n.parameters) {
    const params = n.parameters
      .map((p) => {
        const t = p.type ? checker.typeToString(checker.getTypeFromTypeNode(p.type)) : "any";
        return t;
      })
      .join(",");
    const rt = n.type ? checker.typeToString(checker.getTypeFromTypeNode(n.type)) : "any";
    sig = `fn(${params})->${rt}`;
  } else if (ts.isClassDeclaration(n)) {
    sig = `class{${n.members?.length ?? 0}}`;
  } else if (ts.isInterfaceDeclaration(n)) {
    sig = `iface{${n.members?.length ?? 0}}`;
  } else if (ts.isEnumDeclaration(n)) {
    sig = `enum{${n.members.length}}`;
  } else if (ts.isVariableStatement(n)) {
    sig = `vars{${n.declarationList.declarations.length}}`;
  } else {
    sig = ts.SyntaxKind[n.kind];
  }
  return hash(sig);
}

function normalizePath(p: string): string {
  return p.replace(/\\/g, "/").replace(/^\.\//, "").replace(/^\//, "");
}
