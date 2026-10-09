/*
 * Shapes this package hands to the neosuite-app shell. The shell mounts `routes` under
 * `/<product>`, renders `widgets` by id and registers `context` with NeoMind.
 */
import type { ActionDescriptor } from "@neospacetech/neosuite-schema";
import type { ComponentType } from "react";

export interface ProductRoute {
  /** Path relative to the product's mount point, e.g. `""` or `"lifecycle"`. */
  path: string;
  title: string;
  /** Show in the shell's product navigation. */
  nav: boolean;
  component: ComponentType;
}

export interface WidgetDescriptor<P extends object = Record<string, never>> {
  id: string;
  title: string;
  /** Object type the widget renders, if it renders one. */
  objectType?: string;
  component: ComponentType<P>;
}

/** What the current screen is showing, as reported to NeoMind. */
export interface ContextSnapshot {
  route: string;
  /** Object refs or slugs the user is looking at, most relevant first. */
  selection: string[];
}

export interface ContextDescriptor {
  product: string;
  /** Object types this product owns. */
  types: string[];
  /** Actions NeoMind may suggest; NeoMind invokes them through NeoFlow, never directly. */
  actions: Pick<ActionDescriptor, "id" | "title" | "description" | "effect">[];
  /** Short natural-language summary of what the user is looking at. */
  describe: (snapshot: ContextSnapshot) => string;
}
