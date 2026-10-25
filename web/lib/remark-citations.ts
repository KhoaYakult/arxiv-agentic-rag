// Remark plugin: tach marker [n] trong text node thanh <span class="cite-ref" data-nums>.
// Chi dung toi node "text" -> code/inlineCode (node rieng) tu dong giu nguyen.
import type { Parent, Root, Text } from "mdast";
import { SKIP, visit } from "unist-util-visit";
import { splitCitations } from "@/lib/citations";

export function remarkCitations() {
  return (tree: Root) => {
    visit(tree, "text", (node: Text, index: number | undefined, parent: Parent | undefined) => {
      if (!parent || index === undefined || parent.type === "link" || parent.type === "linkReference") return;
      const segs = splitCitations(node.value);
      if (!segs.some((s) => s.type === "cite")) return;
      const nodes = segs.map((s) =>
        s.type === "text"
          ? ({ type: "text", value: s.value } as Text)
          : ({
              type: "text",
              value: s.raw,
              data: { hName: "span", hProperties: { className: ["cite-ref"], "data-nums": s.nums.join(",") } },
            } as unknown as Text),
      );
      parent.children.splice(index, 1, ...nodes);
      return [SKIP, index + nodes.length];
    });
  };
}
