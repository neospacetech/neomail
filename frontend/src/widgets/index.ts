import type { WidgetDescriptor } from "../module";
import { ItemStatusBadge, type ItemStatusBadgeProps } from "./ItemStatusBadge";

export { ItemStatusBadge, type ItemStatusBadgeProps };

/** Embeddable views other products and NeoMind can render, keyed by stable widget id. */
export const widgets = {
  "neomail.item.status": {
    id: "neomail.item.status",
    title: "Item status",
    objectType: "neomail.Item",
    component: ItemStatusBadge,
  } satisfies WidgetDescriptor<ItemStatusBadgeProps>,
};
