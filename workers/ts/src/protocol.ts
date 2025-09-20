export type File = { path: string; content: string };
export type Snapshot = { files: File[]; project?: string | null };

export type Op = {
  id: string;
  schemaVersion: 1;
  type: string;
  target: { symbolId: string; addressId?: string | null };
  params: any;
  guards: any;
  effects: any;
  provenance: { rev?: string; author?: string; timestamp?: string };
};

export type BuildAndDiffParams = {
  base: Snapshot;
  left: Snapshot;
  right: Snapshot;
  config: { deterministicSeed?: string };
};

export type BuildAndDiffResult = {
  opLogLeft: Op[];
  opLogRight: Op[];
  symbolMaps: Record<string, Array<{ symbolId: string; addressId: string }>>;
  diagnostics: any[];
};
