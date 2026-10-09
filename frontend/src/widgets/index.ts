import type { WidgetDescriptor } from "../module";
import { InboxWidget, type InboxWidgetProps } from "./InboxWidget";

export { InboxWidget, type InboxWidgetProps };

/** Embeddable views other products and NeoMind can render, keyed by stable widget id. */
export const widgets = {
  "neomail.inbox": {
    id: "neomail.inbox",
    title: "Inbox",
    objectType: "neomail.Thread",
    component: InboxWidget,
  } satisfies WidgetDescriptor<InboxWidgetProps>,
};
