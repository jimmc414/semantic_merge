"""C# backend placeholder."""


class CSWorker:
    def build_and_diff(self, base_tree, left_tree, right_tree):
        raise NotImplementedError(
            "Enable the C# backend by integrating Roslyn and exposing the protocol over stdio"
        )
