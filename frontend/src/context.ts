import type { ContextDescriptor } from "./module";

/** NeoMind context and actions for NeoMail. */
export const context: ContextDescriptor = {
  product: "neomail",
  types: ["neomail.Item"],
  actions: [
    {
      id: "neomail.item.transition",
      title: "Move an item to its next status",
      description: "Advance an item one step through todo -> doing -> done.",
      effect: "write",
    },
  ],
  describe: ({ route, selection }) => {
    const where = route === "lifecycle" ? "the lifecycle demo" : "the item list";
    return selection.length > 0 ? `Viewing ${where}; selected item: ${selection[0]}.` : `Viewing ${where}.`;
  },
};
