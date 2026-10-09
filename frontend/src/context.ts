import type { ContextDescriptor } from "./module";

/** NeoMind context and actions for NeoMail. */
export const context: ContextDescriptor = {
  product: "neomail",
  types: ["neomail.Mailbox", "neomail.Thread", "neomail.Message"],
  actions: [
    {
      id: "neomail.message.send",
      title: "Send a message",
      description: "Send an email; Smart Send checks it first and stops on conflicts unless confirmed.",
      effect: "external",
    },
    {
      id: "neomail.message.move",
      title: "Move a message",
      description: "Put a message in other mailboxes, for example to archive it.",
      effect: "write",
    },
    {
      id: "neomail.message.mark",
      title: "Mark a message",
      description: "Mark a message read, unread, flagged or unflagged.",
      effect: "write",
    },
    {
      id: "neomail.smartsend.check",
      title: "Check a draft with Smart Send",
      description: "Check a draft's claims against the sender's calendar and the draft itself.",
      effect: "read",
    },
  ],
  describe: ({ selection }) =>
    selection.length > 0 ? `Reading mail; open conversation: ${selection[0]}.` : "Viewing the mailbox list.",
};
